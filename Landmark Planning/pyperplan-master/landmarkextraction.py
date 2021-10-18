import functools
import re
import sys
from pyperplan import grounding
from pyperplan.pddl.parser import Parser
from pyperplan.planner import _parse, _ground
from pyperplan.search.a_star import astar_search
from pyperplan.heuristics.landmarks import *
from pyperplan.heuristics.lm_cut import LmCutHeuristic
from src.pyperplan.search.a_star import astar_search as astar_search_custom
from pyperplan.heuristics.blind import *
import os

class ExtractLandmarks():
    '''
    self.domainFile - location of the domain file
    self.taskTemplate - template of task pddl file

    self.goals - list of goals
    self.realGoalIndex - the actual goal
    self.landmarks - list of landmarks generated from goals

    self.debug - whether to print debug comments
    '''
    #################
    ### VARIABLES ###
    #################
    TEMP_DIR = os.path.join(os.path.dirname(__file__), "temp") # Location of temp folder

    ###################################
    ### INITIALIZATION OF LANDMARKS ###
    ###################################
    def __init__(self, *args, debug = False):
        '''
        Constructs landmarks out of given domain file, goals list and task template pddl.
        '''
        self.debug = debug
        self.landmarks = []
        if len(args) == 1:
            pass
             # self.__unpackTar(*args)
        elif len(args) == 4:
            self.__unpackFiles(*args)
        else:
            raise TypeError("Incorrect number of arguments.")
        self.optimal_plans = self.generate_optimal() #Remove to improve performance

    def __unpackFiles(self, domaindir, hypsdir, realhypdir, templatedir):
        '''
        Loads the necessary resources into class variables. This function is called when
        three arguments are given.
        '''
        print(f"# Getting landmarks")
        self.domainFile = os.path.abspath(domaindir)
        with open(hypsdir) as goalsfile:
            self.goals = goalsfile.read().splitlines()
        with open(realhypdir) as realhypfile:
            self.realGoalIndex = self.goals.index(realhypfile.readline())
        with open(templatedir) as templatefile:
            self.taskTemplate = templatefile.read()

        # DEBUG
        self.__output(
            '# List of Goals parsed:', 
            *[f"{i} : {a}" for i, a in enumerate(self.goals)]
        )
        self.__output(
            '# Real Goal parsed:', 
            f"{self.realGoalIndex} : {self.goals[self.realGoalIndex]}"
        )

        self.__populate()
    
    def __populate(self):
        '''
        Creates task files for each goal using the template, 
        and uses these task files to extract landmarks.
        '''
        for i in range(len(self.goals)):
            dirname = self.tempLoc(f"task{i}.pddl")
            task = self.taskTemplate.replace("<HYPOTHESIS>", self.goals[i])
            with open(dirname, "w") as create:
                create.write(task)
            parser = Parser(self.domainFile, dirname)
            dom = parser.parse_domain()
            problem = parser.parse_problem(dom)
            task = grounding.ground(problem)
            landmarks = get_landmarks(task)
            landmarks_set = set(map(self.parse_goal, landmarks))
            self.landmarks.append(landmarks_set)
            
        self.__output(
            '# List of Landmarks calculated:',
            *[f"{i} : {self.goals[i]} : {a}" for i, a in enumerate(self.landmarks)]
        )

    ############################################
    ### FUNCTIONS INTERACTING WITH LANDMARKS ###
    ############################################
    def testApproaches(self):
        APPROACHES = [self.approach1, self.approach2, self.approach3]

        def pathToGoal(acc, goal):
            ''' Given a task and a landmark, calculate the number of steps to achieve this landmark
            and calculate the end state after traversing the path.
            '''
            task, steps = acc
            print(f"# Finding path to {goal}")

            task.goals = goal
            heuristic = LandmarkHeuristic(task)
            actual = astar_search_custom(task, heuristic, return_state=True)  # Patrick's edited code
            path = astar_search(task, heuristic)  # Generate a path
            # Applying these ops to the state
            for op in path:
                steps += 1
                print(f"Current State: {task.initial_state}")
                print(f"Applying step {steps}: {op}")
                task.initial_state = op.apply(task.initial_state)
            assert task.initial_state == actual  # Making sure the final state is correct

            print(f"Current step is truthful: {self.is_truthful(task)}")
            return task, steps

        for approach in APPROACHES:
            self.__output(f"##### Approach: {approach} #####")
            parser = Parser(self.domainFile, self.tempLoc("task99.pddl"))
            dom = parser.parse_domain()
            problem = parser.parse_problem(dom)
            initialTask = grounding.ground(problem)

            orderedPath = approach(initialTask)
            task, steps = functools.reduce(pathToGoal, orderedPath, (initialTask, 0))
            calc = self.parse_goal(self.goals[self.realGoalIndex]) 
            assert calc.issubset(task.initial_state)  # check that the goal is indeed reached
            print(f"FINAL RESULT: {steps} steps taken to reach final goal.")

    def approach1(self, initialTask):
        ''' 
        Method for picking landmarks:
            - The goal with the most landmarks in common with the real goal is the most in common.
            
        Method for ordering landmarks:
            - This goal's landmarks are ordered based on similiarity to the initial state.
        ''' 
        def ordering_score(landmark):
            ''' Order landmarks based on similiarity to the initial task '''
            initialTask.goals = landmark
            landmarks = get_landmarks(initialTask)
            h = landmarks - initialTask.initial_state
            print(f"Landmark: {landmark}, Score: {len(h)}")
            return len(h)

        # PICKING LANDMARKS
        landmarkIntersection =  [i.intersection(self.landmarks[self.realGoalIndex]) for i in self.landmarks] 
        landmarkIntersection[self.realGoalIndex] = {} # Intersection with self to empty set
        self.__output(
            "# Intersection of goals with the real goal",
            *[f"{i}: {a} " if i != self.realGoalIndex else "" for i, a in enumerate(landmarkIntersection)])

        landmarkSet = max(landmarkIntersection, key=len) # Result has a list of landmarks
        self.__output(
            "# The intersection with the largest number of landmarks",
            *[f"{i}: {a} " for i, a in enumerate(landmarkSet)])



        # LANDMARK ORDERING
        print(f"# Sorting based on score")
        ordered_l = sorted(landmarkSet, key=lambda landmark: ordering_score(landmark))
        self.__output(f"Sorted based on score: {ordered_l}")
        ordered_l.append(self.parse_goal(self.goals[self.realGoalIndex]))
        return ordered_l

    def approach2(self, initialTask):
        ''' 
        Simply a path to the end.
        ''' 
        ordered_l = []
        ordered_l.append(self.parse_goal(self.goals[self.realGoalIndex]))
        return ordered_l

    def approach3(self, initialTask):
        '''
        Method for picking landmarks:
            - The goal with the most landmarks in common with the real goal is the most in common.
        '''
        landmarkIntersection =  [i.intersection(self.landmarks[self.realGoalIndex]) for i in self.landmarks] 
        landmarkIntersection[self.realGoalIndex] = {} # Intersection with self to empty set
        self.__output(
            "# Intersection of goals with the real goal",
            *[f"{i}: {a} " if i != self.realGoalIndex else "" for i, a in enumerate(landmarkIntersection)])

        landmarkSetIndex = landmarkIntersection.index(max(landmarkIntersection, key=len)) # Result has a list of landmarks
        self.__output(
            "# The index of the goal with the largest number of landmarks in common",
            landmarkSetIndex)
        ordered_l = []
        ordered_l.append(self.parse_goal(self.goals[landmarkSetIndex]))
        ordered_l.append(self.parse_goal(self.goals[self.realGoalIndex]))
        return ordered_l


    ########################
    ### USEFUL FUNCTIONS ###
    ########################

    def __output(self, *lines, result=None):
        ''' Function to make pretty outputs.
        '''
        if self.debug:
            for l in lines:
                print(l)
            if result:
                print(f"Result: {result}")
            print("-----------------")

    def tempLoc(self, name):
        ''' Returns an absolute directory to the temp location.
        '''
        return os.path.join(self.TEMP_DIR, name)

    def outputLoc(self, name):
        ''' Returns an absolute directory to the output location.
        '''
        return os.path.join(self.OUTPUT_DIR, name)

    def setDebug(self, debugMode = True):
        ''' Whether to have outputs.
        '''
        self.debug = debugMode

    def parse_goal(self, goal):
        parsedgoals = re.findall('\([A-Za-z0-9 ]*\)', goal)
        return frozenset(parsedgoals)

    def generate_optimal(self):
        optimal_paths = []
        goal_task = _ground(_parse(self.domainFile, self.tempLoc("task0.pddl")))
        for goal in self.goals:
            print(f"Calculating...")
            goal_task.goals = self.parse_goal(goal)
            heuristic = LmCutHeuristic(goal_task)
            goal_plan = astar_search(goal_task, heuristic)
            optimal_paths.append(len(goal_plan))
            print(f"Calculated length: {len(goal_plan)}")
        return optimal_paths

    def cost_dif(self, goal, state_task):
        '''
        Calculates the cost difference at any state from a goal. Defined in Masters work, means that the difference
        between state and goal can be calculated without relying on previous observations. Formula used is
        costdif(s, g, n) = optc(n, g) - optc(s, g) where optc(state, goal) is the cost of the optimal path from
        state to goal, s = start state, g = goal, n = current state

        @param goal:  Integer specifying goal from self.goals list
        @param state_task: Task instance for current state
        @return: integer representation of difference in length between path to state and path to goal.
        '''

        state_task.goals = self.parse_goal(self.goals[goal])
        heuristic = LmCutHeuristic(state_task)
        state_plan = astar_search(state_task, heuristic)

        return len(state_plan) - self.optimal_plans[goal]

    def is_truthful(self, state_task):
        true_cost_diff = self.cost_dif(self.realGoalIndex, state_task)
        for i in range(len(self.goals)):
            if i == self.realGoalIndex:
                pass
            else:
                if true_cost_diff < self.cost_dif(i, state_task):
                    return True
        return False


    ##################################################
    ### UNUSED STUFF WHICH MIGHT BE HANDY LATER ON ###
    ##################################################
    """
    UNUSED, probably does not work currently
    def __unpackTar(self, tardir):
        '''
        Loads the necessary resources into class variables. This function is called when
        one argument is given.
        '''
        with tarfile.open(tardir, 'r:bz2') as tar:
            tar.extract('domain.pddl', path="temp")
            self.domainfile = os.path.abspath('temp/domain.pddl')
            self.goals = tar.extractfile('hyps.dat').read().decode('utf-8').splitlines()
            self.template = tar.extractfile('template.pddl').read().decode('utf-8')
        self.__populate()
    
    def intersection(self, *args):
        ''' Finds the intersections of landmarks between given goals
        '''
        result = set.intersection(*[self.landmarks[i] for i in args] if len(args) else self.landmarks)
        self.__output(f"Finding intersection of landmarks between goals: {*args,}", result=result)
        return result

    """
    """
    def table(self):
        '''Return a table of the landmark intersection for each pair of goals.
        '''
        data = [[a.intersection(b) for a in self.landmarks] for b in self.landmarks]
        # result = pd.DataFrame(data)
        self.__output(f"Finding intersection table between all landmarks", result= data)
        return data
    """
    """ UNUSED
    def getLandmark(self, landmark = None):
        '''
        Returns a specific landmark, or returns all landmarks depending 
        on whether an argument is given.
        '''
        return self.landmarks if landmark is None else self.landmarks[landmark]

    def getGoal(self, goal = None):
        '''
        Returns a specific goal, or returns all goals depending 
        on whether an argument is given.
        '''
        return self.goals if goal is None else self.goals[goal] 
    """
    
if __name__ == "__main__":
    DIR = os.path.dirname(__file__)
    # Defining constants
    EXPERIMENTS_DIR = os.path.join(DIR, 'experiments/raw')
    EXPERIMENTS_TAR_DIR = os.path.join(DIR, 'experiments/tar')
    RESULTS_DIR = os.path.join(DIR, 'results')
    TEMP_DIR = os.path.join(DIR, 'temp')
    OUTPUT_DIR = os.path.join(DIR, "output") # Location of output folder

    # Iterate through each problem set
    for _, dirs, _ in os.walk(EXPERIMENTS_DIR):
        for dname in dirs:
            domaindir = f"{EXPERIMENTS_DIR}/{dname}/domain.pddl"
            hypsdir = f"{EXPERIMENTS_DIR}/{dname}/hyps.dat"
            realhypdir = f"{EXPERIMENTS_DIR}/{dname}/real_hyp.dat"
            templatedir = f"{EXPERIMENTS_DIR}/{dname}/template.pddl"
            #sys.stdout = open(os.path.join(OUTPUT_DIR, f"{dname}result.txt"), 'w+')
            extraction = ExtractLandmarks(domaindir, hypsdir, realhypdir, templatedir, debug=True)
            extraction.testApproaches()

    # For TAR files
    '''
    for _, _, files in os.walk(EXPERIMENTS_TAR_DIR):
        for tarfname in files:
            extraction = ExtractLandmarks(f"{EXPERIMENTS_TAR_DIR}/{tarfname}")
    '''