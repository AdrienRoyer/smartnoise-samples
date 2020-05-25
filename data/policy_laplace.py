from collections import defaultdict
import operator
import copy
import numpy as np
import itertools

class PolicyLaplace:
    def __init__(self, epsilon, delta, alpha, tokens_per_user, budget_per_user=None):
        Delta_0 = tokens_per_user
        self.Delta = budget_per_user if budget_per_user else 1  # budget per user

        l_param = 1 / epsilon
        F_l_rho = lambda t: 1 / t + (1 / epsilon) * np.log(1 / (2 * (1 - (1 - delta) ** (1 / t))))
        l_rho = np.max([F_l_rho(t) for t in range(1, Delta_0 + 1)])
        Gamma=l_rho + alpha*l_param
        self.Gamma = Gamma
        self.Delta_0 = Delta_0 # tokens_per_user
        self.l_param = l_param
        self.l_rho = l_rho

        print("Params Delta_0={0}, delta={1:.2e}, l_param={2}, l_rho={3}, Gamma={4}".format(Delta_0, delta, l_param, l_rho, Gamma))

    
    def exceeds_threshold(self, val):
        nval = val + np.random.laplace(0, self.l_param)
        if nval > self.l_rho:
            return True
        else:
            return False

    def reservoir_sample(self, user_tokens_rdd, distinct=True):
        """Takes an RDD with (user, tokens) and combines all tokens from all users,
            then samples uniformly to get at most tokens_per_user tokens.  User is not
            assumed to be grouped or sorted on input stream, and users may appear more
            than once, with different lists of tokens.
        """
        tokens_per_user = self.Delta_0
        if tokens_per_user == 1:
            return user_tokens_rdd

        def selected_grams(row):
            user, tokens = row
            all_grams = list(itertools.chain.from_iterable(tokens))
            if distinct:
                all_grams = list(set(all_grams))
            if tokens_per_user > 1 and len(all_grams) > tokens_per_user:
                selected = np.random.choice(all_grams, size=tokens_per_user, replace=False).tolist()
            else:
                selected = all_grams
            return (user, selected)

        return user_tokens_rdd.groupByKey().map(selected_grams)



    def process_rows(self, rows):
        ngram_hist = defaultdict(float)
        rowsl = list(rows)
        for row in rowsl:
            user, selected_ngrams = row
            gap_dict = {}

            ngl = list(selected_ngrams)
            for w in ngl:
                if ngram_hist[w] < self.Gamma:
                    gap_dict[w] = self.Gamma - ngram_hist[w]
            # sort rho dict
            sorted_gap_dict = sorted(gap_dict.items(), key=operator.itemgetter(1))

            sorted_gap_keys = [k for k, v in sorted_gap_dict]

            budget = copy.copy(self.Delta)
            total_tokens = len(sorted_gap_keys)

            for i, w in enumerate(sorted_gap_keys):
                cost = gap_dict[w]*(total_tokens-i)
                if cost < budget:
                    for j in range(i, total_tokens):
                        add_gram = sorted_gap_keys[j]
                        ngram_hist[add_gram] += gap_dict[w]
                    # update remaining budget
                    budget -= cost
                    # update dictionary of values containing difference from gap
                    for key in gap_dict: 
                        gap_dict[key] -= gap_dict[w] 
                else:
                    for j in range(i, total_tokens):
                        add_gram = sorted_gap_keys[j]
                        ngram_hist[add_gram] += budget/(total_tokens-i)
                    break
        yield ngram_hist