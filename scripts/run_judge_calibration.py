"""Optional consistency statistic; it does not generate solver answers."""
import collections
def consistency(first,second):
    a={r['id']:r['score'] for r in first};b={r['id']:r['score'] for r in second}
    if set(a)!=set(b) or not a:raise ValueError('Calibration rounds must have identical nonempty IDs')
    n=len(a);agree=sum(a[k]==b[k] for k in a)/n
    da=collections.Counter(a.values());db=collections.Counter(b.values())
    chance=sum(da[k]*db[k] for k in (0,1,2))/n**2
    return {'sample_count':n,'exact_agreement_rate':agree,
            'mean_absolute_score_difference':sum(abs(a[k]-b[k]) for k in a)/n,
            'cohens_kappa':(agree-chance)/(1-chance) if chance<1 else None,
            'score_distribution_round_1':{str(k):da[k] for k in (0,1,2)},
            'score_distribution_round_2':{str(k):db[k] for k in (0,1,2)},
            'disagreement_ids':[k for k in a if a[k]!=b[k]]}
