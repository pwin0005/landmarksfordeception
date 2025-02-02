import functools
import re
from pyperplan import grounding
from pyperplan.pddl.parser import Parser
from pyperplan.planner import _parse, _ground
from pyperplan.search.a_star import astar_search
from pyperplan.heuristics.landmarks import *
from pyperplan.heuristics.lm_cut import LmCutHeuristic
from src.pyperplan.search.a_star import astar_search as astar_search_custom
from pyperplan.heuristics.blind import *
import os
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

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
    def __init__(self, *args, debug = False) -> None:
        '''
        Constructs landmarks out of given domain file, goals list and task template pddl.
        '''
        self.debug = debug
        self.landmarks = []
        self.initialTask = None
        if len(args) == 1:
            pass
            # self.__unpackTar(*args)
        elif len(args) == 4:
            self.__unpackFiles(*args)
        else:
            raise TypeError("Incorrect number of arguments.")
        self.optimal_plans = self.generate_optimal()

    def __unpackFiles(self, domaindir, hypsdir, realhypdir, templatedir) -> None:
        '''
        Loads the necessary resources into class variables. This function is called when
        three arguments are given.
        '''
        print(f"##### Getting landmarks #####")
        self.domainFile: str = os.path.abspath(domaindir)
        with open(hypsdir) as goalsfile:
            self.goals: list[str] = goalsfile.read().splitlines()
        with open(realhypdir) as realhypfile:
            self.realGoalIndex: int = self.goals.index(realhypfile.readline())
        with open(templatedir) as templatefile:
            self.taskTemplate: str = templatefile.read()

        # DEBUG
        print( '# List of Goals parsed: #\n', 
            *[f"{i} : {a}\n" for i, a in enumerate(self.goals)] )
        print( '# Real Goal parsed: #\n', 
            f"{self.realGoalIndex} : {self.goals[self.realGoalIndex]}\n" )

        self.__populate()
    
    def __populate(self) -> None:
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
            if self.initialTask == None:
                self.initialTask = task
            landmarks = get_landmarks(task)
            landmarks_set = set(map(self.parse_goal, landmarks))
            self.landmarks.append(landmarks_set)
            
        print('# List of Landmarks calculated:\n',
            *[f"{i} : {self.goals[i]} : {a}\n" for i, a in enumerate(self.landmarks)] )

    def tempLoc(self, name):
        ''' Returns an absolute directory to the temp location.
        '''
        return os.path.join(self.TEMP_DIR, name)

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

    def getRealGoal(self, parse = False):
        return self.getGoal(self.realGoalIndex, parse)

    def getGoal(self, index, parse = False):
        goal = self.goals[index]
        return self.parse_goal(goal) if parse else goal

    def getRealLandmark(self, parse = False):
        return self.getLandmark(self.realGoalIndex, parse)
    
    def getLandmark(self, index, parse = False):
        landmark = self.landmarks[index]
        return self.parse_goal(landmark) if parse else landmark

class ApproachTemplate():
    def __init__(self, extractedLandmarks: ExtractLandmarks):
        self.l = extractedLandmarks

    def generate(self):
        pass

class BaselineApproach(ApproachTemplate):
    NAME = "Baseline Approach"
    DESCRIPTION = """
    Calculates a path from the initial state to the real goal.
    """
    def __init__(self, extractedLandmarks: ExtractLandmarks):
        super().__init__(extractedLandmarks)
        
    def generate(self):
        ordered_l = []
        ordered_l.append(self.l.getRealGoal(True))
        return ordered_l

class GoalToRealGoalApproach(ApproachTemplate):
    NAME = "Goal to Real Goal Approach"
    DESCRIPTION = """
    Calculates a path from the initial state to a candidate goal which has the 
    most landmarks in common with the real goal.
    """
    def __init__(self, extractedLandmarks: ExtractLandmarks):
        super().__init__(extractedLandmarks)

    def generate(self):
        '''
        Method for picking landmarks:
            - The goal with the most landmarks in common with the real goal is the most in common.
        '''
        landmarkIntersection =  [i.intersection(self.l.getRealLandmark()) for i in self.l.landmarks] 
        landmarkIntersection[self.l.realGoalIndex] = {} # Intersection with self to empty set
        print(
            "# Intersection of goals with the real goal",
            *[f"{i}: {a} " if i != self.l.realGoalIndex else "" for i, a in enumerate(landmarkIntersection)])
        print(landmarkIntersection)
        landmarkSetIndex = landmarkIntersection.index(max(landmarkIntersection, key=len)) # Result has a list of landmarks
        print(
            "# The index of the goal with the largest number of landmarks in common",
            landmarkSetIndex)

        ordered_l = []
        ordered_l.append(self.l.getGoal(landmarkSetIndex, True))
        ordered_l.append(self.l.getRealGoal(True))
        return ordered_l

class OldScoringApproach(ApproachTemplate):
    NAME = "Old Scoring Approach"
    DESCRIPTION = """
        Travels to each landmark which is ordered by the number of "sub landmarks" it covers
        """
    def __init__(self, extractedLandmarks: ExtractLandmarks):
        super().__init__(extractedLandmarks)
        

    def generate(self):
        ''' 
        Method for picking landmarks:
            - The goal with the most landmarks in common with the real goal is the most in common.
            
        Method for ordering landmarks:
            - This goal's landmarks are ordered based on similiarity to the initial state.
        ''' 
        def ordering_score(landmark):
            ''' Order landmarks based on similiarity to the initial task '''
            initialTask = self.l.initialTask
            initialTask.goals = landmark
            landmarks = get_landmarks(initialTask) # get the landmarks of this landmark
            print(f"LANDMARKS:{landmark} : {landmarks}")
            print(f"Landmark: {landmark}, Score: {len(landmarks)}")
            return len(landmarks)

        # PICKING LANDMARKS
        landmarkIntersection =  [i.intersection(self.l.getRealLandmark()) for i in self.l.landmarks] 
        landmarkIntersection[self.l.realGoalIndex] = {} # Intersection with self to empty set
        print(
            "# Intersection of goals with the real goal",
            *[f"{i}: {a} " if i != self.l.realGoalIndex else "" for i, a in enumerate(landmarkIntersection)])

        landmarkSet = max(landmarkIntersection, key=len) # Result has a list of landmarks
        print(
            "# The intersection with the largest number of landmarks",
            *[f"{i}: {a} " for i, a in enumerate(landmarkSet)])

        # LANDMARK ORDERING
        print(f"# Sorting based on score")
        print(landmarkSet)
        ordered_l = sorted(landmarkSet, key=lambda landmark: ordering_score(landmark))
        print(f"Sorted based on score: {ordered_l}")
        ordered_l.append(self.l.getRealGoal(True))
        return ordered_l

class NewScoringApproach(ApproachTemplate):
    NAME = "New Scoring Approach"
    DESC = """
    Travels to each landmark which is ordered by the number of "sub landmarks" it covers
    """
    def __init__(self, extractedLandmarks: ExtractLandmarks):
        super().__init__(extractedLandmarks)

    def generate(self):
        mem_dict = {}
        # PICKING LANDMARKS
        def ordering_score(landmark):
            ''' Order landmarks based on similiarity to the initial task '''
            score = mem_dict.get(landmark)
            if not score:
                # calculate score if it isnt already in the dictionary
                initialTask = self.l.initialTask
                initialTask.goals = landmark
                landmarks = get_landmarks(initialTask) # get the landmarks of this landmark
                landmarks = landmarks - landmark
                score = sum([ordering_score(self.l.parse_goal(lm)) for lm in landmarks]) + 1
                print(f"{landmark} : {score}")
                mem_dict[landmark] = score
            return score

        landmarkIntersection =  [i.intersection(self.l.getRealLandmark()) for i in self.l.landmarks] 
        landmarkIntersection[self.l.realGoalIndex] = {} # Intersection with self to empty set
        print(
            "# Intersection of goals with the real goal",
            *[f"{i}: {a} " if i != self.l.realGoalIndex else "" for i, a in enumerate(landmarkIntersection)])

        maximumIntersectionIndex = landmarkIntersection.index(max(landmarkIntersection, key=len)) # Result has an index of the maximum intersection
        closestLandmarks = self.l.getLandmark(maximumIntersectionIndex)
        realGoalLandmarks = self.l.getRealLandmark()
        combinedLandmarks = closestLandmarks.union(realGoalLandmarks)
        sortedLandmarks = sorted(combinedLandmarks, key=lambda landmark: ordering_score(landmark))
        sortedLandmarks.append(self.l.getRealGoal(True))
        return(sortedLandmarks)

class ApproachTester():
    ############################################
    ### FUNCTIONS INTERACTING WITH LANDMARKS ###
    ############################################
    def __init__(self, *args: ApproachTemplate, extracted: ExtractLandmarks):
        self.approaches = [*args]
        self.l = extracted
    
    def testApproaches(self):
        def pathToGoal(acc, goal):
            ''' Given a task and a landmark, calculate the number of steps to achieve this landmark
            and calculate the end state after traversing the path. Deception keeps track of whether FTP and LDP have been reached in form of (BOOLEAN,BOOLEAN)
            '''
            task, steps, deception_array = acc
            print(f"###### Finding path to {goal} #####")

            task.goals = goal
            heuristic = LandmarkHeuristic(task)
            actual = astar_search_custom(task, heuristic, return_state=True)  # Patrick's edited code
            path = astar_search(task, heuristic)  # Generate a path
            # Applying these ops to the state
            for op in path:
                steps += 1
                print(f"Current State: {task.initial_state}")
                print(f"Applying step {steps}: {op}")
                task.initial_state = op.apply(task.initial_state) #TODO Check deceptivity here rather than at landmarks

                deception_array.append(self.deceptive_stats(task))
            assert task.initial_state == actual  # Making sure the final state is correct
            return task, steps, deception_array

        for approach in self.approaches:
            print(f"##### Approach: {approach.NAME} #####")
            parser = Parser(self.l.domainFile, self.l.tempLoc("task0.pddl"))
            dom = parser.parse_domain()
            problem = parser.parse_problem(dom)
            initialTask = grounding.ground(problem)
            orderedPath = approach(self.l).generate()
            task, steps, deception_array = functools.reduce(pathToGoal, orderedPath, (initialTask, 0, []))
            calc = self.l.getRealGoal(True)
            assert calc.issubset(task.initial_state)  # check that the goal is indeed reached
            print(f"FINAL RESULT: {steps} steps taken to reach final goal.")
            deceptive_stats = self.calc_deceptive_stats(deception_array)
            self.plot(deception_array, approach)
            print(f"Density of deception: {deceptive_stats[0]}")
            print(f"Extent of deception: {deceptive_stats[1]}")

    def plot(self, deception_array, approach):
        dir = "temp/"
        plt.figure(figsize=(10,8))
        plt.title(f"Approach Type: {approach.NAME}")
        pathlength = self.l.optimal_plans[self.l.realGoalIndex]
        df = pd.DataFrame(deception_array, columns = ['deceptive', 'deceptiveness'])
        for i in range(len(df)):
            color = 'r' if df['deceptive'][i] else 'b'
            plt.scatter(i, -1*(df['deceptiveness'][i] - pathlength), color = color)
        # 
        plt.xlabel("Steps")
        plt.ylabel("Optimal Steps to Goal",)
        plt.legend(handles = [mpatches.Patch(color='r', label='Non-Deceptive'), mpatches.Patch(color='b', label='Deceptive')])
        plt.savefig(os.path.join(os.path.dirname(__file__), "output") + f"/{approach.NAME}.png")
    ########################
    ### USEFUL FUNCTIONS ###
    ########################

    def optc(self, goal, state_task): #TODO Refactor to output path completion as well as cost_dif
        '''
        Calculates the optimal cost from current state to goal. Can be used to calculate cost diff and probability distributions.

        @param goal:  Integer specifying goal from self.goals list
        @param state_task: Task instance for current state
        @return: integer representation of length of path from current state to the given goal.
        '''
        original_goal = state_task.goals
        state_task.goals = self.l.getGoal(goal, True)
        heuristic = LmCutHeuristic(state_task)
        state_plan = astar_search(state_task, heuristic)
        state_task.goals = original_goal
        return len(state_plan)

    def deceptive_stats(self, state_task):
        '''
        Calculates statistics related to deception for a certain state such as truthfulness and plan completion.
        @param state_task: Task instance for current state
        @return:
        '''
        opt_state_to_goal = self.optc(self.l.realGoalIndex, state_task)
        true_cost_diff = opt_state_to_goal - self.l.optimal_plans[self.l.realGoalIndex]
        truthful = False
        for i in range(len(self.l.goals)):
            if i == self.l.realGoalIndex:
                pass
            else:
                if true_cost_diff < (self.optc(i, state_task) - self.l.optimal_plans[i]):
                    truthful = True
        plan_completion = self.l.optimal_plans[self.l.realGoalIndex] - opt_state_to_goal
        return truthful, plan_completion

    def calc_deceptive_stats(self, deception_array):
        truths = 0
        LDP_path_comp = 0
        for state in deception_array:
            if state[0]:
                truths += 1
            else:
                LDP_path_comp = state[1]
        return 1/truths, LDP_path_comp

if __name__ == "__main__":
    DIR = os.path.dirname(__file__)
    # Defining constants
    EXPERIMENTS_DIR = os.path.join(DIR, 'experiments/patrick')
    # EXPERIMENTS_DIR = os.path.join(DIR, 'experiments/raw')
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
            extracted = ExtractLandmarks(domaindir, hypsdir, realhypdir, templatedir, debug=True)
            a1 = ApproachTester(BaselineApproach, GoalToRealGoalApproach, OldScoringApproach, NewScoringApproach, extracted = extracted)
            a1.testApproaches()