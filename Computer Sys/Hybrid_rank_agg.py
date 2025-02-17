from pyspark import SparkContext
from scipy import sparse as sm
from sklearn.preprocessing import normalize
import numpy as np
import csv
from sklearn.metrics.pairwise import cosine_similarity
from scipy.stats import pearsonr as pears
from collections import defaultdict
sc = SparkContext.getOrCreate()


train_rdd = sc.textFile("data/train.csv")
icm_rdd = sc.textFile("data/icm_fede.csv")
test_rdd= sc.textFile("data/target_users.csv")

train_header = train_rdd.first()
icm_header = icm_rdd.first()
test_header= test_rdd.first()

train_clean_data = train_rdd.filter(lambda x: x != train_header).map(lambda line: line.split(',')).map(lambda x: (int(x[0]), int(x[1]), float(x[2])))
icm_clean_data = icm_rdd.filter(lambda x: x != icm_header).map(lambda line: line.split(',')).map(lambda x: (int(x[0]), int(x[1])))
test_clean_data= test_rdd.filter(lambda x: x != test_header).map(lambda line: line.split(','))

test_users=test_clean_data.map( lambda x: int(x[0])).collect()


grouped_rates = train_clean_data.filter(lambda x: x[0] in test_users).map(lambda x: (x[0],x[1])).groupByKey().map(lambda x: (x[0], list(x[1]))).collect()
grouped_rates_dic = dict(grouped_rates)


item_ratings = train_clean_data.map(lambda x: (x[0], x[2])).aggregateByKey((0,0), lambda x,y: (x[0] + y, x[1] + 1),lambda x,y: (x[0] + y[0], x[1] + y[1]))
user_ratings_mean = item_ratings.mapValues(lambda x: (x[0] / (x[1]))).collect()
user_ratings_mean_dic=dict(user_ratings_mean)


item_ratings_forTop = train_clean_data.map(lambda x: (x[1], x[2])).aggregateByKey((0,0), lambda x,y: (x[0] + y, x[1] + 1),lambda x,y: (x[0] + y[0], x[1] + y[1]))#.sortBy(lambda x: x[1][1], ascending=False)
#item_ratings.take(10)
shrinkage_factor = 5
item_ratings_mean = item_ratings_forTop.mapValues(lambda x: (x[0] / (x[1] + shrinkage_factor))).sortBy(lambda x: x[1], ascending = False).map(lambda x: x[0]).collect()


users = train_clean_data.map(lambda x: x[0]).collect()
items = train_clean_data.map(lambda x: x[1]).collect()
ratings = train_clean_data.map(lambda x: x[2]).collect()
ratings_unbiased = train_clean_data.map(lambda x: x[2]-user_ratings_mean_dic[x[0]]).collect()

items_for_features= icm_clean_data.map(lambda x:x[0]).collect()
features = icm_clean_data.map(lambda x:x[1]).collect()
items_for_features.append(37142)
features.append(0)


unos=[1]*len(items_for_features)

UxI= sm.csr_matrix((ratings, (users, items)))
UxI_unbiased= sm.csr_matrix((ratings_unbiased, (users, items)))
IxF= sm.csr_matrix((unos, (items_for_features, features)))

'''begin of content based'''
IxF_normalized=normalize(IxF,axis=1)
NumItems,NumFeatures=IxF.shape
NumFeatures
IDF=[0]*NumFeatures
for i in range(NumFeatures):
    IDF[i]=np.log10(NumItems/len(IxF.getcol(i).nonzero()[1]))
UxF=UxI.dot(IxF_normalized)
FxI=IxF_normalized.multiply(IDF).T
UxI_pred_CB=UxF.dot(FxI)

'''contet versione prof'''
IxF_idf=IxF.multiply(IDF)
IxI_sim=sm.csr_matrix(cosine_similarity(IxF_idf))
IxI_sim.setdiag(0)
UxI_pred_CBS=UxI.dot(normalize(IxI_sim,axis=0,norm='l1' ))

'''begin of cf user based'''
UxU_sim_dafile=sc.textFile("users-users-sims.csv").map(lambda x: x.replace("(","").replace(")","").replace(" ","").split(",")).map(lambda x: (int(x[0]), int(x[1]), float(x[2])))
us1=UxU_sim_dafile.map(lambda x:x[0]).collect()
us2=UxU_sim_dafile.map(lambda x:x[1]).collect()
simsus=UxU_sim_dafile.map(lambda x:x[2]).collect()
UxU_sim= sm.csr_matrix((simsus, (us1, us2)))
UxU_sim.setdiag(0)
UxI_pred_CFU=UxU_sim.dot(UxI_unbiased)

'''begin of cf item based'''
IxI_sim_dafile=sc.textFile("items-items-sims.csv").map(lambda x: x.replace("(","").replace(")","").replace(" ","").split(",")).map(lambda x: (int(x[0]), int(x[1]), float(x[2])))
it1=IxI_sim_dafile.map(lambda x:x[0]).collect()
it2=IxI_sim_dafile.map(lambda x:x[1]).collect()
simsit=IxI_sim_dafile.map(lambda x:x[2]).collect()
IxI_sim= sm.csr_matrix((simsit, (it1, it2)))
IxI_sim.setdiag(0)
UxI_pred_CFI=UxI_unbiased.dot(IxI_sim)

'''collaborative su items-features'''
IxI_sim_fromfeatures=IxF_normalized(IxF_normalized.T)
IxI_sim_fromfeatures.setdiag(0)
UxI_pred_CFF=UxI.dot(IxI_sim_fromfeatures)

UxI_pred_CB.toarray()
UxI_pred_CBS.toarray()

ciao = defaultdict(list)
ciao[3] = [4]
ciao[3].pop()
ciao.keys()
del ciao[3]
ciao.keys()
def medRank(user,rank1,rank2):
    top=list()
    counterDic = defaultdict(int)
    orderedDic = defaultdict(list)
    already_voted=grouped_rates_dic[user]
    nrRanks=2
    doR1=True
    doR2=True

    for i in range(len(rank1)):
        #se non è stato beccato un rating predetto a 0 in questo rank
        if doR1:
            #prendi il rating massimo
            item1=rank1.argmax()
            #se il rating massimo non è zero
            if rank1[item1] > 0.0:
                rank1[item1]=-9
                if item1 not in already_voted:
                    count = counterDic[item1]
                    counterDic[item1]+=1
                    if counterDic[item1] >= nrRanks:
                        top+=[item1]
                        orderedDic[count].remove(item1)
                    else:
                        if count > 0:
                            orderedDic[count].remove(item1)
                        orderedDic[count + 1] += [item1]
                if len(top)>=5:
                    break
            #altrimenti smetti di prendere in considerazione questo rank
            else:
                doR1=False
                #nrRanks-=1

        if doR2:
            item2=rank2.argmax()
            if rank2[item2] > 0.0:
                rank2[item2]=-9
                if item2 not in already_voted:
                    count = counterDic[item2]
                    counterDic[item2]+=1
                    if counterDic[item2] >= nrRanks:
                        top+=[item2]
                        orderedDic[count].remove(item2)
                    else:
                        if count > 0:
                            orderedDic[count].remove(item2)
                        orderedDic[count + 1] += [item2]
                if len(top)>=5:
                    break
            else:
                doR2=False

        if not doR1 and not doR2:
            break


    max_rank = max(list(orderedDic.keys()))
    while len(orderedDic[max_rank]) == 0:
        del orderedDic[max_rank]
        max_rank = max(list(orderedDic.keys()))

    for i in range(5 - len(top)):
        top += orderedDic[max_rank].pop(0)
        if len(orderedDic[max_rank]) == 0:
            del orderedDic[max_rank]
            max_rank = max(list(orderedDic.keys()))
    return top




c=0
f = open('submission_CF_sum.csv', 'wt')
writer = csv.writer(f)
writer.writerow(('userId','RecommendedItemIds'))
for user in test_users:

    top=medRank(user,UxI_pred_CB.getrow(user),UxI_pred_CBS.getrow(user))

    iterator = 0
    for i in range(5 - len(top)):
        while (item_ratings_mean[iterator] in grouped_rates_dic[user]) or (item_ratings_mean[iterator] in top):
            iterator = iterator + 1
        top += [item_ratings_mean[iterator]]



    c+=1
    print(c)
    writer.writerow((user, '{0} {1} {2} {3} {4}'.format(top[0], top[1], top[2], top[3], top[4])))

f.close()



def bordaAggr(rank1,rank2,rank3,rank4):
    nrItems=UxI.shape[1]
    result=[0]*nrItems
    rg=100
    for i in range(rg):
        item1=rank1.argmax()
        item2=rank2.argmax()
        item3=rank3.argmax()
        item4=rank4.argmax()

        if rank1[item1]>0.0:
            result[item1]+=((rg-i)*5.8)
        rank1[item1]=-9

        if rank2[item2]>0.0:
            result[item2]+=((rg-i)*3.6)
        rank2[item2]=-9

        if rank3[item3]>0.0:
            result[item3]+=((rg-i)*2)
        rank3[item3]=-9

        if rank4[item4]>0.0:
            result[item4]+=((rg-i)*1)
        rank4[item4]=-9

    return sm.csr_matrix(result)


c=0
f = open('submission_borda_100_5.8_3.6_2_1_.csv', 'wt')
writer = csv.writer(f)
writer.writerow(('userId','RecommendedItemIds'))
for user in test_users:
    top=[0,0,0,0,0]

    user_predictions=bordaAggr(UxI_pred_CB.getrow(user).toarray()[0],UxI_pred_CBS.getrow(user).toarray()[0],UxI_pred_CFU.getrow(user).toarray()[0],UxI_pred_CFI.getrow(user).toarray()[0])
    iterator = 0
    for i in range(5):
        prediction = user_predictions.argmax()
        while prediction in grouped_rates_dic[user] and prediction != 0:
            user_predictions[0,prediction]=-9
            prediction=user_predictions.argmax()
        if prediction == 0:
            prediction = item_ratings_mean[iterator]
            while prediction in grouped_rates_dic[user] or prediction in top:
                iterator += 1
                prediction = item_ratings_mean[iterator]
            iterator += 1
        else:
            user_predictions[0,prediction]=-9
        top[i]=prediction
    c+=1
    print(c)
    writer.writerow((user, '{0} {1} {2} {3} {4}'.format(top[0], top[1], top[2], top[3], top[4])))

f.close()
