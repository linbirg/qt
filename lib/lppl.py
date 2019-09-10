import random
import math
import numpy as np
from scipy.optimize import fmin_tnc

# 需要初始化才能使用
g_times = []
g_closes = []

g_flag_lppl = 1  # 1 lppl, -1 re-lppl


def set_closes(closes):
    global g_times
    global g_closes

    g_closes = closes
    g_times = np.linspace(0, len(closes) - 1, len(closes))


def set_lppl_flag(yes_or_no):
    global g_flag_lppl
    g_flag_lppl = 1 if yes_or_no else -1


def get_DataSeries():
    # global g_times
    # global g_closes

    return [g_times, g_closes]


def lppl(t, x):
    ''' return fitting result using LPPL parameters '''
    a = x[0]
    b = x[1]
    tc = x[2]
    m = x[3]
    c = x[4]
    w = x[5]
    phi = x[6]
    delta_t = g_flag_lppl * (tc - t)

    return a + (b * np.power(delta_t, m)) * (1 + (c * np.cos(
        (w * np.log(delta_t) + phi))))


def func(x):
    # global g_times
    # global g_closes
    # 生成lppl时间序列
    delta = [lppl(t, x) for t in g_times]
    # 将生成的lppl时间序列减去对数指数序列
    delta = np.subtract(delta, g_closes)
    delta = np.power(delta, 2)
    # 返回拟合均方差
    return np.sum(delta)


# def fitFunc(t, a, b, tc, m, c, w, phi):
#     return a - (b * np.power(tc - t, m)) * (1 + (c * np.cos(
#         (w * np.log(tc - t)) + phi)))


class Individual:
    '''base class for individuals'''

    def __init__(self, InitValues):
        self.fit = 0
        self.cof = InitValues

    def fitness(self):
        try:
            cofs, _, _ = fmin_tnc(
                func, self.cof, fprime=None, approx_grad=True, messages=0)
            self.fit = func(cofs)
            self.cof = cofs
            if math.isnan(self.fit):
                return False
        except:
            # does not converge
            return False

    # 交配
    def mate(self, partner):
        reply = []
        for i in range(0, len(self.cof)):  # 遍历所以的输入参数
            if (random.randint(
                    0, 1) == 1):  # 交配，0.5的概率自身的参数保留，0.5的概率留下partner的参数，即基因交换
                reply.append(self.cof[i])
            else:
                reply.append(partner.cof[i])

        return Individual(reply)

    # 突变
    def mutate(self):
        for i in range(0, len(self.cof) - 1):
            if random.randint(0, len(self.cof)) <= 2:
                # print "Mutate" + str(i)
                self.cof[i] += random.choice([-1, 1]) * .05 * i  # 突变

    # 打印结果
    def print_individual(self):
        # t, a, b, tc, m, c, w, phi
        cofs = "A: " + str(round(self.cof[0], 3))
        cofs += " B: " + str(round(self.cof[1], 3))
        cofs += " Critical Time: " + str(round(self.cof[2], 3))
        cofs += " m: " + str(round(self.cof[3], 3))
        cofs += " c: " + str(round(self.cof[4], 3))
        cofs += " omega: " + str(round(self.cof[5], 3))
        cofs += " phi: " + str(round(self.cof[6], 3))

        return "fitness: " + str(self.fit) + "\n" + cofs

    def get_DataSeries(self):
        # global g_times
        # global g_closes
        return get_DataSeries()

    def get_ExpData(self):
        # global g_times
        return [lppl(t, self.cof) for t in g_times]

    def get_expre_data(self, times):
        return [lppl(t, self.cof) for t in times]


class Population:
    'base class for a population'
    LOOP_MAX = 1500

    def __init__(self, limits, size, eliminate, mate, probmutate):
        '''seeds the population'
        limits is a tuple holding the lower and upper limits of the cofs
        size is the size of the seed population'''
        self.populous = []
        self.eliminate = eliminate
        self.size = size
        self.mate = mate
        self.probmutate = probmutate
        self.fitness = []

        for _ in range(size):
            SeedCofs = [random.uniform(a[0], a[1]) for a in limits]
            self.populous.append(Individual(SeedCofs))

    def PopulationPrint(self):
        for x in self.populous:
            print(x.cof)

    def SetFitness(self):
        self.fitness = [x.fit for x in self.populous]

    def FitnessStats(self):
        # returns an array with high, low, mean
        return [
            np.amax(self.fitness),
            np.amin(self.fitness),
            np.mean(self.fitness)
        ]

    def Fitness(self):
        counter = 0
        false = 0
        for individual in list(self.populous):
            print('Fitness Evaluating: ', counter, " of ", len(self.populous),
                  "        \r")
            state = individual.fitness()
            counter += 1

            if state == False:
                false += 1
                self.populous.remove(individual)
        self.SetFitness()
        print("\n fitness out size: " + str(len(self.populous)) + " false:" +
              str(false))

    def Eliminate(self):
        a = len(self.populous)
        self.populous.sort(key=lambda ind: ind.fit)
        while len(self.populous) > self.size * self.eliminate:
            self.populous.pop()
        print("Eliminate: " + str(a - len(self.populous)))

    def Mate(self):
        counter = 0
        while len(self.populous) <= self.mate * self.size:
            counter += 1
            i = self.populous[random.randint(0, len(self.populous) - 1)]
            j = self.populous[random.randint(0, len(self.populous) - 1)]
            diff = abs(i.fit - j.fit)
            if (diff < random.uniform(
                    np.amin(self.fitness),
                    np.amax(self.fitness) - np.amin(self.fitness))):
                self.populous.append(i.mate(j))

            if counter > Population.LOOP_MAX:
                print("loop broken: mate")
                while len(self.populous) <= self.mate * self.size:
                    i = self.populous[random.randint(0,
                                                     len(self.populous) - 1)]
                    j = self.populous[random.randint(0,
                                                     len(self.populous) - 1)]
                    self.populous.append(i.mate(j))

        print("Mate Loop complete: " + str(counter))

    def Mutate(self):
        counter = 0
        for ind in self.populous:
            if random.uniform(0, 1) < self.probmutate:
                ind.mutate()
                ind.fitness()
                counter += 1
        print("Mutate: " + str(counter))
        self.SetFitness()

    def BestSolutions(self, num):
        reply = []
        self.populous.sort(key=lambda ind: ind.fit)
        # flted = [ind for ind in self.populous if not math.isnan(ind.fit)]
        for i in range(num):
            reply.append(self.populous[i])
        return reply

    random.seed()
