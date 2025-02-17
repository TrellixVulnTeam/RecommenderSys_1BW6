from collections import defaultdict
from itertools import combinations, permutations
import random
import numpy as np
import pdb
import csv
from pyspark import SparkContext


def parseVector(line):
    '''
    Parse each line of the specified data file, assuming a "|" delimiter.
    Converts each rating to a float
    '''
    line = line.split(",")
    return int(line[0]),int(line[1]),float(line[2])

def parseVectorOnUser(line):
    '''
    Parse each line of the specified data file, assuming a "|" delimiter.
    Key is user_id, converts each rating to a float.
    '''
    line = line.split(",")
    return line[0],(line[1],float(line[2]))

def parseVectorOnItem(line):
    '''
    Parse each line of the specified data file, assuming a "|" delimiter.
    Key is item_id, converts each rating to a float.
    '''
    line = line.split(",")
    return line[1],(line[0],float(line[2]))

def sampleInteractions(item_id,users_with_rating,n):
    '''
    For items with # interactions > n, replace their interaction history
    with a sample of n users_with_rating
    '''
    if len(users_with_rating) > n:
        return item_id, random.sample(users_with_rating,n)
    else:
        return item_id, users_with_rating

def findUserPairs(item_id,users_with_rating):
    '''
    For each item, find all user-user pairs combos. (i.e. users with the same item)
    '''
    result = list()
    for user1,user2 in permutations(users_with_rating,2):
        result += [((user1[0],user2[0]),(user1[1],user2[1]))]
    return result

def calcSim(user_pair,rating_pairs):
    '''
    For each user-user pair, return the specified similarity measure,
    along with co_raters_count.
    '''
    sum_xx, sum_xy, sum_yy, sum_x, sum_y, n = (0.0, 0.0, 0.0, 0.0, 0.0, 0)

    for rating_pair in rating_pairs:
        sum_xx += np.float(rating_pair[0]) * np.float(rating_pair[0])
        sum_yy += np.float(rating_pair[1]) * np.float(rating_pair[1])
        sum_xy += np.float(rating_pair[0]) * np.float(rating_pair[1])
        # sum_y += rt[1]
        # sum_x += rt[0]
        n += 1

    cos_sim = cosine(sum_xy,np.sqrt(sum_xx),np.sqrt(sum_yy))
    return user_pair, (cos_sim,n)

shrinkage_factor_cosine = 4

def cosine(dot_product,rating_norm_squared,rating2_norm_squared):
    '''
    The cosine between two vectors A, B
       dotProduct(A, B) / (norm(A) * norm(B))
    '''
    numerator = dot_product
    denominator = rating_norm_squared * rating2_norm_squared# + shrinkage_factor_cosine

    return (numerator / (float(denominator))) if denominator else 0.0

def keyOnFirstUser(user_pair,item_sim_data):
    '''
    For each user-user pair, make the first user's id the key
    '''
    (user1_id,user2_id) = user_pair
    return user1_id,(user2_id,item_sim_data)

def nearestNeighbors(user,users_and_sims,n):
    '''
    Sort the predictions list by similarity and select the top-N neighbors
    '''
    users_and_sims.sort(key=lambda x: x[1][0],reverse=True)
    return user, users_and_sims[:n]

def topNRecommendations(user_id,user_sims,users_with_rating,n):
    '''
    Calculate the top-N item recommendations for each user using the
    weighted sums method
    '''

    # initialize dicts to store the score of each individual item,
    # since an item can exist in more than one item neighborhood
    totals = defaultdict(int)
    sim_sums = defaultdict(int)
    already_voted = grouped_rates_dic[user_id]
    for (neighbor,(sim,count)) in user_sims:

        # lookup the item predictions for this neighbor
        unscored_items = users_with_rating.get(neighbor,None)

        if unscored_items:
            for (item,rating) in unscored_items:
                #if neighbor != item:

                # update totals and sim_sums with the rating data
                totals[item] += sim * rating
                sim_sums[item] += sim

    # create the normalized list of scored items
    #se voglio rating allora + media
    #users_ratings_mean[user_id]
    #/sim_sums[item]
    scored_items = [(total,item) for item,total in totals.items() if sim_sums[item] != 0 and not item in already_voted]
    #
    # sort the scored items in ascending order
    scored_items.sort(reverse=True)

    # take out the item score
    ranked_items = [x[1] for x in scored_items]
    #ranked_items = scored_items
    return user_id,ranked_items[:n]


sc = SparkContext.getOrCreate()

train_rdd = sc.textFile("../data/train.csv")
test_rdd= sc.textFile("../data/target_users.csv")

train_header = train_rdd.first()
test_header= test_rdd.first()

train_clean_data = train_rdd.filter(lambda x: x != train_header).map(parseVector)
test_clean_data = test_rdd.filter(lambda x: x != test_header).map(lambda line: line.split(','))
#train_clean_data = sc.parallelize([(1,1,2.5),(1,2,-1.5),(1,4,-0.5),(1,5,-0.5),(2,1,-2.6),(2,2,1.4),(2,3,-1.6),(2,4,1.4),(2,5,1.4),(3,1,-1.5),(3,3,-0.5),(3,4,1.5),(3,5,0.5),(4,1,0.25),(4,2,-0.75),(4,3,1.25),(4,4,-0.75)])

train_clean_data.cache()
test_clean_data.cache()

test_users=test_clean_data.map(lambda x: int(x[0])).collect()
#test_users = [1,2,3,4]

grouped_rates = train_clean_data.filter(lambda x: x[0] in test_users).map(lambda x: (x[0],x[1])).groupByKey().map(lambda x: (x[0], list(x[1]))).collect()
grouped_rates_dic = dict(grouped_rates)

users_ratings = train_clean_data.map(lambda x: (x[0], x[2])).aggregateByKey((0,0), lambda x,y: (x[0] + y, x[1] + 1),lambda x,y: (x[0] + y[0], x[1] + y[1]))
users_ratings_mean = dict(users_ratings.mapValues(lambda x: (x[0] / x[1])).collect())

item_ratings = train_clean_data.map(lambda x: (x[1], x[2])).aggregateByKey((0,0), lambda x,y: (x[0] + y, x[1] + 1),lambda x,y: (x[0] + y[0], x[1] + y[1]))#.sortBy(lambda x: x[1][1], ascending=False)
shrinkage_factor = 10
item_ratings_mean = item_ratings.mapValues(lambda x: (x[0] / (x[1] + shrinkage_factor))).sortBy(lambda x: x[1], ascending = False).map(lambda x: x[0]).collect()


#Obtain the sparse item-user matrix: item_id -> ((user_1,rating),(user2,rating))

item_user_pairs = train_clean_data.map(lambda x: (x[1], (x[0], x[2] - users_ratings_mean[x[0]]))).groupByKey().map(lambda p: sampleInteractions(p[0],p[1],1700)).cache()
#item_user_pairs = train_clean_data.map(lambda x: (x[1], (x[0], x[2]))).groupByKey().map(lambda p: sampleInteractions(p[0],p[1],1700)).cache()

#Get all item-item pair combos: (user1_id,user2_id) -> [(rating1,rating2), (rating1,rating2),

pairwise_users = item_user_pairs.filter(
    lambda p: len(p[1]) > 1).flatMap(
    lambda p: findUserPairs(p[0],p[1])).groupByKey()

#Calculate the cosine similarity for each user pair and select the top-N nearest neighbors: (user1,user2) ->    (similarity,co_raters_count)


user_sims = pairwise_users.map(
    lambda p: calcSim(p[0],p[1])).map(
    lambda p: keyOnFirstUser(p[0],p[1])).groupByKey().map(
    lambda p: nearestNeighbors(p[0],list(p[1]),50))

#Obtain the the item history for each user and store it as a broadcast variable user_id -> [(item_id_1, rating_1), [(item_id_2, rating_2),
user_item_hist = train_clean_data.map(lambda x: (x[0], (x[1], x[2] - users_ratings_mean[x[0]]))).groupByKey().collect()
#user_sims.collect()
ui_dict = {}
for (user,items) in user_item_hist:
    ui_dict[user] = items

uib = sc.broadcast(ui_dict)

#Calculate the top-N item recommendations for each user user_id -> [item1,item2,item3,...]
user_item_recs = user_sims.filter(lambda x: x[0] in test_users).map(
    lambda p: topNRecommendations(p[0],p[1],uib.value,5)).sortByKey().collect()

#user_item_recs[:100]

recs_dict = dict(user_item_recs)

def parseSubmission(line):
    user, items = line.split(",")
    items = items.split(" ")
    return (int(user), [int(item) for item in items])

submission_rdd = sc.textFile("submission.csv")
submission_header = submission_rdd.first()
submission_clean_data = submission_rdd.filter(lambda x: x != submission_header).map(parseSubmission).collect()
#submission_clean_data[:2]
submission_clean_data_dic = dict(submission_clean_data)

f = open('../submission_no_shrinkage.csv', 'wt')

writer = csv.writer(f)
writer.writerow(('userId','RecommendedItemIds'))

for u in test_users:

    predictions = recs_dict.get(u, [])
    iterator = 0
    already_voted = grouped_rates_dic[u]
    content_based_items = submission_clean_data_dic[u]
    for i in range(5 - len(predictions)):
        while (content_based_items[iterator] in already_voted) or (content_based_items[iterator] in predictions):
            iterator = iterator + 1
        predictions = predictions + [content_based_items[iterator]]
    writer.writerow((u, '{0} {1} {2} {3} {4}'.format(predictions[0], predictions[1], predictions[2], predictions[3], predictions[4])))
    #i+=1
    #print(i)

f.close()

'''
for i in range(5 - len(predictions)):
    while (item_ratings_mean[iterator] in already_voted) or (item_ratings_mean[iterator] in predictions):
        iterator = iterator + 1
    predictions = predictions + [item_ratings_mean[iterator]]
'''
