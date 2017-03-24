"""Main DQN agent."""

from keras import optimizers
from keras.layers import (Activation, Conv2D, Dense, Flatten, Input,Multiply,BatchNormalization)
from keras.models import Model
import numpy as np
import pickle
import matplotlib.pyplot as plt

import deeprl_hw2 as tfrl
from copy import deepcopy

DEBUG=0

GAMMA = 0.99
ALPHA = 1e-4
EPSILON = 0.05
REPLAY_BUFFER_SIZE = 1000000
BATCH_SIZE = 32
IMG_ROWS , IMG_COLS = 84, 84
WINDOW = 4
TARGET_QNET_RESET_INTERVAL = 10000
SAMPLES_BURN_IN = 10000
TRAINING_FREQUENCY=4
MOMENTUM = 0.8
NUM_RAND_STATE = 1000
UPDATE_OFFSET = 100
EVALUATION_FREQUENCY=10000


class QNAgent:
    
    """Class implementing DQN.

    This is a basic outline of the functions/parameters you will need
    in order to implement the DQNAgnet. This is just to get you
    started. You may need to tweak the parameters, add new ones, etc.

    Feel free to change the functions and funciton parameters that the
    class provides.

    We have provided docstrings to go along with our suggested API.

    Parameters
    ----------
    q_network: keras.models.Model
      Your Q-network model.
    preprocessor: deeprl_hw2.core.Preprocessor
      The preprocessor class. See the associated classes for more
      details.
    memory: deeprl_hw2.core.Memory
      Your replay memory.
    gamma: float
      Discount factor.
    target_update_freq: float
      Frequency to update the target network. You can either provide a
      number representing a soft target update (see utils.py) or a
      hard target update (see utils.py and Atari paper.)
    num_burn_in: int
      Before you begin updating the Q-network your replay memory has
      to be filled up with some number of samples. This number says
      how many.
    train_freq: int
      How often you actually update your Q-Network. Sometimes
      stability is improved if you collect a couple samples for your
      replay memory, for every Q-network update that you run.
    batch_size: int
      How many samples in each minibatch.
    """
    def __init__(self,
                 network_type,
                 num_actions,
                 preprocessors,
                 memory,
                 burnin_policy,
                 observing_policy,
                 training_policy,
                 testing_policy,
                 gamma=GAMMA,
                 alpha=ALPHA,
                 target_update_freq=TARGET_QNET_RESET_INTERVAL,
                 num_burn_in=SAMPLES_BURN_IN,
                 train_freq=TRAINING_FREQUENCY,
                 eval_freq=EVALUATION_FREQUENCY,
                 batch_size=BATCH_SIZE):


        self.network_type 	= network_type
        self.num_actions	= num_actions
        self.atari_proc  	= preprocessors[0]
        self.hist_proc  	= preprocessors[1]
        self.preproc     	= preprocessors[2]

        print 'model summary'
   

        self.memory	 	= memory
        self.observing_policy 	= observing_policy
        self.burnin_policy      = burnin_policy
        self.testing_policy 	= testing_policy
        self.training_policy 	= training_policy
        self.gamma 		= gamma
        self.target_update_freq = target_update_freq
        self.num_burn_in 	= num_burn_in
        self.train_freq		= train_freq
        self.eval_freq      	= eval_freq
        self.batch_size		= batch_size
        self.num_updates 	= 0
        self.num_samples    	= 0
        self.total_reward  	= []
        self.alpha 		= alpha
        self.train_loss		= []
        self.mean_q		= []
        self.rand_states 	= np.zeros((NUM_RAND_STATE, 4, 84, 84))
        self.rand_states_mask 	= np.ones((NUM_RAND_STATE, self.num_actions))
        self.input_dummymask = np.ones((1,self.num_actions))
        self.input_dummymask_batch=np.ones((self.batch_size, self.num_actions))

    def create_dueling_model(self, window, input_shape, num_actions):  # noqa: D103
        """Create a deep network for the Q-network model.
            Parameters
            ----------
            window: int
            Each input to the network is a sequence of frames. This value
            defines how many frames are in the sequence.
            input_shape: tuple(int, int)
            The expected input image size.
            num_actions: int
            Number of possible actions. Defined by the gym environment.
            model_name: str
            Useful when debugging. Makes the model show up nicer in tensorboard.
            
            Returns
            -------
            keras.models.Model
            The Q-model.
        """
        
        a1 = Input(shape=(window,input_shape[0],input_shape[1]))
        a2 = Input(shape=(num_actions,))
        b = Conv2D(32, (8, 8), strides=4, padding='same',use_bias=True, data_format='channels_first')(a1)
        bn = BatchNormalization(axis=1)(b)
        b = Activation ('relu')(bn)
        c = Conv2D(64, (4, 4), strides=2, padding='same',use_bias=True, data_format='channels_first')(b)
        cn = BatchNormalization(axis=1)(c)
        c = Activation ('relu')(cn)

        d = Conv2D(64, (3, 3), strides=1, padding='same',use_bias=True, data_format='channels_first')(c)
        dn = BatchNormalization(axis=1)(d)
        d = Activation ('relu')(dn)

        d = Flatten()(d)
        e1 = Dense(512)(d)
        e2 = Dense(512)(d)
        e1 = Activation ('relu')(e1)
        e2 = Activation ('relu')(e2)
        f_adv = Dense(num_actions)(e1)
        f_adv = Activation ('linear')(f_adv)
	f_adv_mean = GlobalAveragePooling1D()(f_adv)
        f_val = Dense(1)(e2)
        f_val = Activation ('linear')(f_val)
	f_val_minus_mean = Add()([f_val,-f_adv_mean])
        f_val_minus_mean = RepeatVector(num_actions)(f_val_minus_mean)
        f_val_minus_mean = Flatten()(f_val_minus_mean)
	f = Add()([f_adv, f_val_minus_mean])
        h = Multiply()([f,a2])
        model = Model(inputs=[a1,a2], outputs=[h])
                          
        return model

    def create_deep_model(self, window, input_shape, num_actions):  # noqa: D103
        """Create a deep network for the Q-network model.
            Parameters
            ----------
            window: int
            Each input to the network is a sequence of frames. This value
            defines how many frames are in the sequence.
            input_shape: tuple(int, int)
            The expected input image size.
            num_actions: int
            Number of possible actions. Defined by the gym environment.
            model_name: str
            Useful when debugging. Makes the model show up nicer in tensorboard.
            
            Returns
            -------
            keras.models.Model
            The Q-model.
        """
        
        a1 = Input(shape=(window,input_shape[0],input_shape[1]))
        a2 = Input(shape=(num_actions,))
        b = Conv2D(16, (8, 8), strides=4, padding='same',use_bias=True, data_format='channels_first')(a1)
        bn = BatchNormalization(axis=1)(b)
        b = Activation ('relu')(bn)
        c = Conv2D(32, (4, 4), strides=2, padding='same',use_bias=True, data_format='channels_first')(b)
        cn = BatchNormalization(axis=1)(c)
        c = Activation ('relu')(cn)
        d = Flatten()(c)
        e = Dense(256)(d)
        e = Activation ('relu')(e)
        f = Dense(num_actions)(e)
        f = Activation ('linear')(f)
        h = Multiply()([f,a2])
        model = Model(inputs=[a1,a2], outputs=[h])
                          
        return model


                          
    def create_linear_model(self, window, input_shape, num_actions):  # noqa: D103
        """Create a linear network for the Q-network model.
            
            Parameters
            ----------
            window: int
            Each input to the network is a sequence of frames. This value
            defines how many frames are in the sequence.
            input_shape: tuple(int, int)
            The expected input image size.
            num_actions: int
            Number of possible actions. Defined by the gym environment.
            model_name: str
            Useful when debugging. Makes the model show up nicer in tensorboard.
            
            Returns
            -------
            keras.models.Model
            The Q-model.
            """
                
        a1 = Input(shape=(window,input_shape[0],input_shape[1]))
        a2 = Input(shape=(num_actions,))
        b = Flatten()(a1)
        c = Dense(num_actions)(b)
        e = Multiply()([c,a2])
        model = Model(inputs=[a1,a2], outputs=[e])
            
        return model


    def calc_q_values(self, state):
        """Given a state (or batch of states) calculate the Q-values.

        Basically run your network on these states.

        Return
        ------
        Q-values for the state(s)
        """
        q_values =  self.q_network.predict(state, batch_size = 1)
	#print 'shape from calc_q_values {0}'.format(q_values.shape)
	return q_values

    def calc_qt_values(self, state):
        """Given a state (or batch of states) calculate the Q-values.

        Basically run your network on these states.

        Return
        ------
        Q-values for the state(s)
        """
        return self.qt_network.predict(state, batch_size = 1)

    def select_action(self, policy,**kwargs):
        """Select the action based on the current state.

        You will probably want to vary your behavior here based on
        which stage of training your in. For example, if you're still
        collecting random samples you might want to use a
        UniformRandomPolicy.

        If you're testing, you might want to use a GreedyEpsilonPolicy
        with a low epsilon.

        If you're training, you might want to use the
        LinearDecayGreedyEpsilonPolicy.

        This would also be a good place to call
        process_state_for_network in your preprocessor.

        Returns
        --------
        selected action
        """
    
        if policy == 'observing':
                if 'state' in kwargs:
                    return self.observing_policy.select_action(self.calc_q_values(kwargs['state']))
                else:
                    return self.observing_policy.select_action()
        elif policy == 'training':
                if 'state' in kwargs:
                    return self.training_policy.select_action(self.calc_q_values(kwargs['state']), self.num_updates)
                else:
                    return self.training_policy.select_action()
        elif policy == 'testing':
                if 'state' in kwargs:
                    return self.testing_policy.select_action(self.calc_q_values(kwargs['state']))
                else:
                    return self.testing_policy.select_action()
        elif policy == 'burnin':
                if 'state' in kwargs:
                    return self.burnin_policy.select_action(self.calc_q_values(kwargs['state']))
                else:
                    return self.burnin_policy.select_action()

    def fit(self, env, num_iterations, max_episode_length=None):
        """Fit your model to the provided environment.

        Its a good idea to print out things like loss, average reward,
        Q-values, etc to see if your agent is actually improving.

        You should probably also periodically save your network
        weights and any other useful info.

        This is where you should sample actions from your network,
        collect experience samples and add them to your replay memory,
        and update your network parameters.

        Parameters
        ----------
        env: gym.Env
          This is your Atari environment. You should wrap the
          environment using the wrap_atari_env function in the
          utils.py
        num_iterations: int
          How many samples/updates to perform.
        max_episode_length: int
          How long a single episode should last before the agent
          resets. Can help exploration.
        """
        
        env.reset()
        self.hist_proc.reset()
        action = self.select_action(policy='burnin')
        nextstate, reward, is_terminal, debug_info = env.step(action)
        nextstate_history = deepcopy(self.preproc.get_history_for_memory(nextstate))

        for step in range(self.num_burn_in):
            state_history = np.copy(nextstate_history)
            action = self.select_action(policy='burnin')
            nextstate, reward, is_terminal, debug_info = env.step(action)
            nextstate_history = self.preproc.get_history_for_memory(nextstate)
            nextstate_history_float = self.preproc.get_history_for_network(nextstate)
            self.memory.append(state_history, \
                                   action, \
                                   self.atari_proc.process_reward(reward), \
                                   nextstate_history, \
                                   is_terminal)
            self.num_samples += 1
            if self.num_samples >= UPDATE_OFFSET and self.num_samples < NUM_RAND_STATE + UPDATE_OFFSET:
                self.rand_states[self.num_samples-UPDATE_OFFSET,:,:,:] = np.squeeze(nextstate_history_float)
        
        print '=========== Memory burn in ({0}) finished =========='.format(self.num_burn_in)
        
	num_episode = 0
	exp_num=3
        while self.num_samples < num_iterations:
            
            self.hist_proc.reset()
            state = env.reset()
            state_history = self.preproc.get_history_for_memory(state)
            state_history_float = self.preproc.get_history_for_network(state)

            for step in range(max_episode_length):
              
                action = self.select_action(policy='training',state=[state_history_float, self.input_dummymask])
                nextstate, reward, is_terminal, debug_info = env.step(action)
                nextstate_history = self.preproc.get_history_for_memory(nextstate)
                nextstate_history_float = self.preproc.get_history_for_network(nextstate)
                self.memory.append(state_history, \
                                        action, \
                                        self.atari_proc.process_reward(reward), \
                                        nextstate_history, \
                                        is_terminal)
                state_history = np.copy(nextstate_history)
                state_history_float = np.copy(nextstate_history_float)
                
                if self.num_samples % self.train_freq == 0:
                    self.update_policy()
        	    self.num_updates += 1 
                
                self.num_samples += 1
                
                if is_terminal:
		    print 'Game terminates after {0} samples and {1} updates'.format(self.num_samples-self.num_burn_in, self.num_updates)
                    break
	
	    num_episode += 1

	    if num_episode % 100 == 0:
		    print "======================= evaluating source network ============================="
		    self.evaluate(env,10,max_episode_length)
		    plt.plot(self.total_reward)
		    plt.savefig('ftdqn_reward_q_{0}_{1}.jpg'.format(self.network_type,exp_num))
		    plt.close()
        self.q_network.save_weights('ftdqn_source_{0}_{1}.weight'.format(self.network_type, exp_num))
        self.qt_network.save_weights('ftdqn_target_{0}_{1}.weight'.format(self.network_type, exp_num))


    def eval_avg_q(self):
        return np.mean(np.amax(self.calc_q_values([self.rand_states, self.rand_states_mask]), axis=1))

    def evaluate(self, env, num_episodes, max_episode_length=None):
        """Test your agent with a provided environment.
        
        You shouldn't update your network parameters here. Also if you
        have any layers that vary in behavior between train/test time
        (such as dropout or batch norm), you should set them to test.

        Basically run your policy on the environment and collect stats
        like cumulative reward, average episode length, etc.

        You can also call the render function here if you want to
        visually inspect your policy.
        """
        
        total_reward = 0
        for episode_idx in range(num_episodes):
        
            state=env.reset()
            self.hist_proc.reset()
            state_history = deepcopy(self.preproc.get_history_for_network(state))
            
            for step in range(max_episode_length):
                
                action = self.select_action(policy='testing',state=[state_history, self.input_dummymask])
                
                state, reward, is_terminal, debug_info = env.step(action)
                state_history = deepcopy(self.preproc.get_history_for_network(state))
                
                total_reward+=reward
                
                if is_terminal:
                    break

        self.total_reward.append(total_reward)

    def update_policy(self):
        """Update your policy.
            
            Behavior may differ based on what stage of training your
            in. If you're in training mode then you should check if you
            should update your network parameters based on the current
            step and the value you set for train_freq.
            
            Inside, you'll want to sample a minibatch, calculate the
            target values, update your network, and then update your
            target values.
            
            You might want to return the loss and other metrics as an
            output. They can help you monitor how training is going.
            """

        raise NotImplementedError('This method should be overriden.')

    def save_data(self):
        """Update your policy.
        
            Behavior may differ based on what stage of training your
            in. If you're in training mode then you should check if you
            should update your network parameters based on the current
            step and the value you set for train_freq.
        
            Inside, you'll want to sample a minibatch, calculate the
            target values, update your network, and then update your
            target values.
        
            You might want to return the loss and other metrics as an
            output. They can help you monitor how training is going.
        """
        raise NotImplementedError('This method should be overriden.')
    
    def compile(self, optimizer, loss_func):
        """Setup all of the TF graph variables/ops.
            
            This is inspired by the compile method on the
            keras.models.Model class.
            
            This is a good place to create the target network, setup your
            loss function and any placeholders you might need.
            
            You should use the mean_huber_loss function as your
            loss_function. You can also experiment with MSE and other
            losses.
            
            The optimizer can be whatever class you want. We used the
            keras.optimizers.Optimizer class. Specifically the Adam
            optimizer.
            """
        
        raise NotImplementedError('This method should be overriden.')

class FTDQNAgent(QNAgent):
    
    """Class implementing DQN.
        
        This is a basic outline of the functions/parameters you will need
        in order to implement the DQNAgnet. This is just to get you
        started. You may need to tweak the parameters, add new ones, etc.
        
        Feel free to change the functions and funciton parameters that the
        class provides.
        
        We have provided docstrings to go along with our suggested API.
        
        Parameters
        ----------
        q_network: keras.models.Model
        Your Q-network model.
        preprocessor: deeprl_hw2.core.Preprocessor
        The preprocessor class. See the associated classes for more
        details.
        memory: deeprl_hw2.core.Memory
        Your replay memory.
        gamma: float
        Discount factor.
        target_update_freq: float
        Frequency to update the target network. You can either provide a
        number representing a soft target update (see utils.py) or a
        hard target update (see utils.py and Atari paper.)
        num_burn_in: int
        Before you begin updating the Q-network your replay memory has
        to be filled up with some number of samples. This number says
        how many.
        train_freq: int
        How often you actually update your Q-Network. Sometimes
        stability is improved if you collect a couple samples for your
        replay memory, for every Q-network update that you run.
        batch_size: int
        How many samples in each minibatch.
        """
    def __init__(self,
                 network_type,
                 num_actions,
                 preprocessors,
                 memory,
                 burnin_policy,
                 observing_policy,
                 training_policy,
                 testing_policy,
                 gamma=GAMMA,
                 alpha=ALPHA,
                 target_update_freq=TARGET_QNET_RESET_INTERVAL,
                 num_burn_in=SAMPLES_BURN_IN,
                 train_freq=TRAINING_FREQUENCY,
                 eval_freq=EVALUATION_FREQUENCY,
                 batch_size=BATCH_SIZE):

        QNAgent.__init__(self,network_type,num_actions,preprocessors,memory,burnin_policy,observing_policy,training_policy,testing_policy,gamma,alpha,target_update_freq,num_burn_in,train_freq,eval_freq,batch_size)

        if network_type=='LINEAR':
	      self.qt_network  	= self.create_linear_model(window = WINDOW, \
							input_shape = (IMG_ROWS, IMG_COLS), \
							num_actions = self.num_actions)
    
	      self.q_network   	= self.create_linear_model(window = WINDOW, \
						    input_shape = (IMG_ROWS, IMG_COLS), \
						    num_actions = self.num_actions)
        elif network_type=='DEEP':
                              
	      self.qt_network  	= self.create_deep_model(window = WINDOW, \
						   input_shape = (IMG_ROWS, IMG_COLS), \
						   num_actions = self.num_actions)
                              
	      self.q_network   	= self.create_deep_model(window = WINDOW, \
						   input_shape = (IMG_ROWS, IMG_COLS), \
						   num_actions = self.num_actions)

	      #self.qt_network.load_weights('ftdqn_target_DEEP.weight')
	      #self.q_network.load_weights('ftdqn_source_DEEP.weight')

    def compile(self, optimizer, loss_func):
        """Setup all of the TF graph variables/ops.
        
            This is inspired by the compile method on the
            keras.models.Model class.
        
            This is a good place to create the target network, setup your
            loss function and any placeholders you might need.
        
            You should use the mean_huber_loss function as your
            loss_function. You can also experiment with MSE and other
            losses.
        
            The optimizer can be whatever class you want. We used the
            keras.optimizers.Optimizer class. Specifically the Adam
            optimizer.
        """
            
        if optimizer == 'Adam':
            opti = optimizers.Adam(lr=self.alpha)
            self.q_network.compile(loss=loss_func, optimizer = opti)

    def update_policy(self):
        """Update your policy.
            
            Behavior may differ based on what stage of training your
            in. If you're in training mode then you should check if you
            should update your network parameters based on the current
            step and the value you set for train_freq.
            
            Inside, you'll want to sample a minibatch, calculate the
            target values, update your network, and then update your
            target values.
            
            You might want to return the loss and other metrics as an
            output. They can help you monitor how training is going.
        """
                
        # generate batch samples for CNN
        mem_samples = self.memory.sample(self.batch_size)
        mem_samples = self.atari_proc.process_batch(mem_samples)
        input_state_batch=np.zeros((self.batch_size, 4, 84, 84))
        input_nextstate_batch=np.zeros((self.batch_size, 4, 84, 84))
        input_mask_batch=np.zeros((self.batch_size,self.num_actions))
        output_target_batch=np.zeros((self.batch_size,self.num_actions))
        
        for ind in range(self.batch_size):
            input_state_batch[ind,:,:,:] = mem_samples[ind].state
            input_nextstate_batch[ind,:,:,:] = mem_samples[ind].next_state
            input_mask_batch[ind, mem_samples[ind].action] = 1
        
        target_q = self.qt_network.predict([input_nextstate_batch, self.input_dummymask_batch],batch_size=self.batch_size)
        best_target_q = np.amax(target_q, axis=1)
	if DEBUG:
        	print 'best Q values of batch {0}'.format(best_target_q)
        for ind in range(self.batch_size):
            output_target_batch[ind, mem_samples[ind].action] = mem_samples[ind].reward + self.gamma*best_target_q[ind]
        
        temp_loss = self.q_network.train_on_batch(x=[input_state_batch, input_mask_batch], y=output_target_batch)

    
	if self.num_updates % (self.target_update_freq/100) == 0:
            self.train_loss.append(temp_loss)
	    self.mean_q.append(self.eval_avg_q())

	if self.num_updates % self.target_update_freq == 0:
	    self.save_data()
	    print "======================= Sync target and source network ============================="
	    tfrl.utils.get_hard_target_model_updates(self.qt_network, self.q_network)


    def save_data(self):
	exp_num = 3
        plt.plot(self.mean_q)
        plt.savefig('ftdqn_mean_q_{0}_{1}.jpg'.format(self.network_type, exp_num))
        plt.close()
        plt.plot(self.train_loss)
        plt.savefig('ftdqn_train_loss_{0}_{1}.jpg'.format(self.network_type, exp_num))
        plt.close()
        #with open('ftdqn_mean_q_{0}_{1}.data'.format(self.network_type, exp_num),'w') as f:
        #    pickle.dump(self.mean_q,f)
        #with open('ftdqn_train_loss_{0}_{1}.data'.format(self.network_type, exp_num),'w') as f:
        #    pickle.dump(self.train_loss,f)
        #self.q_network.save_weights('ftdqn_source_{0}_{1}.weight'.format(self.network_type, exp_num))
        #self.qt_network.save_weights('ftdqn_target_{0}_{1}.weight'.format(self.network_type, exp_num))


class DDQNAgent(QNAgent):
    
    """Class implementing DQN.
        
        This is a basic outline of the functions/parameters you will need
        in order to implement the DQNAgnet. This is just to get you
        started. You may need to tweak the parameters, add new ones, etc.
        
        Feel free to change the functions and funciton parameters that the
        class provides.
        
        We have provided docstrings to go along with our suggested API.
        
        Parameters
        ----------
        q_network: keras.models.Model
        Your Q-network model.
        preprocessor: deeprl_hw2.core.Preprocessor
        The preprocessor class. See the associated classes for more
        details.
        memory: deeprl_hw2.core.Memory
        Your replay memory.
        gamma: float
        Discount factor.
        target_update_freq: float
        Frequency to update the target network. You can either provide a
        number representing a soft target update (see utils.py) or a
        hard target update (see utils.py and Atari paper.)
        num_burn_in: int
        Before you begin updating the Q-network your replay memory has
        to be filled up with some number of samples. This number says
        how many.
        train_freq: int
        How often you actually update your Q-Network. Sometimes
        stability is improved if you collect a couple samples for your
        replay memory, for every Q-network update that you run.
        batch_size: int
        How many samples in each minibatch.
        """
    def __init__(self,
                 network_type,
                 num_actions,
                 preprocessors,
                 memory,
                 burnin_policy,
                 observing_policy,
                 training_policy,
                 testing_policy,
                 gamma=GAMMA,
                 alpha=ALPHA,
                 target_update_freq=TARGET_QNET_RESET_INTERVAL,
                 num_burn_in=SAMPLES_BURN_IN,
                 train_freq=TRAINING_FREQUENCY,
                 eval_freq=EVALUATION_FREQUENCY,
                 batch_size=BATCH_SIZE):
        
        QNAgent.__init__(self,network_type,num_actions,preprocessors,memory,burnin_policy, observing_policy,training_policy,testing_policy,gamma,alpha,target_update_freq,num_burn_in,train_freq,eval_freq,batch_size)
        
        if network_type=='LINEAR':
            self.qt_network  	= self.create_linear_model(window = WINDOW, \
                                                       input_shape = (IMG_ROWS, IMG_COLS), \
                                                       num_actions = self.num_actions, \
                                                       )

            self.q_network   	= self.create_linear_model(window = WINDOW, \
                                                       input_shape = (IMG_ROWS, IMG_COLS), \
                                                       num_actions = self.num_actions
                                                       )
        elif network_type=='DEEP':

            self.qt_network  	= self.create_deep_model(window = WINDOW, \
                                                     input_shape = (IMG_ROWS, IMG_COLS), \
                                                     num_actions = self.num_actions
                                                     )

            self.q_network   	= self.create_deep_model(window = WINDOW, \
                                                     input_shape = (IMG_ROWS, IMG_COLS), \
                                                     num_actions = self.num_actions
                                                     )

    def update_policy(self):
        """Update your policy.
            
            Behavior may differ based on what stage of training your
            in. If you're in training mode then you should check if you
            should update your network parameters based on the current
            step and the value you set for train_freq.
            
            Inside, you'll want to sample a minibatch, calculate the
            target values, update your network, and then update your
            target values.
            
            You might want to return the loss and other metrics as an
            output. They can help you monitor how training is going.
            """
            
        # generate batch samples for CNN
        mem_samples = self.memory.sample(self.batch_size)
        mem_samples = self.atari_proc.process_batch(mem_samples)
        input_state_batch=np.zeros((self.batch_size, 4, 84, 84))
        input_nextstate_batch=np.zeros((self.batch_size, 4, 84, 84))
        input_mask_batch=np.zeros((self.batch_size,self.num_actions))
        output_target_batch=np.zeros((self.batch_size,self.num_actions))
        
        for ind in range(self.batch_size):
            input_state_batch[ind,:,:,:] = mem_samples[ind].state
            input_nextstate_batch[ind,:,:,:] = mem_samples[ind].next_state
            input_mask_batch[ind, mem_samples[ind].action] = 1


        aux_q = self.q_network.predict([input_nextstate_batch, self.input_dummymask_batch],batch_size=1)
        best_actions=np.argmax(aux_q,axis=1)
        target_q = self.qt_network.predict([input_nextstate_batch, self.input_dummymask_batch],batch_size=1)
        best_target_q = target_q[range(self.batch_size), best_actions]
        
        #print 'best Q values of batch'
        #print best_target_q
        for ind in range(self.batch_size):
            output_target_batch[ind, mem_samples[ind].action] = mem_samples[ind].reward + self.gamma*best_target_q[ind]

        temp_loss = self.q_network.train_on_batch(x=[input_state_batch, input_mask_batch], y=output_target_batch)

	if self.num_updates % (self.target_update_freq/100) == 0:
            self.train_loss.append(temp_loss)
	    self.mean_q.append(self.eval_avg_q())

	if self.num_updates % self.target_update_freq == 0:
	    self.save_data()
	    print "======================= Sync target and source network ============================="
	    tfrl.utils.get_hard_target_model_updates(self.qt_network, self.q_network)
        


    def save_data(self):
        plt.plot(self.mean_q)
        plt.savefig('ddqn_mean_q_{0}.jpg'.format(self.network_type))
        plt.close()
        plt.plot(self.train_loss)
        plt.savefig('ddqn_train_loss_{0}.jpg'.format(self.network_type))
        plt.close()
        #with open('ddqn_mean_q_{0}.data'.format(self.network_type),'w') as f:
        #    pickle.dump(self.mean_q,f)
        #with open('ddqn_train_loss_{0}.data'.format(self.network_type),'w') as f:
        #    pickle.dump(self.train_loss,f)

        #self.q_network.save_weights('ddqn_source_{0}.weight'.format(self.network_type))
        #self.qt_network.save_weights('ddqn_target_{0}.weight'.format(self.network_type))
    
    def compile(self, optimizer, loss_func):
        if optimizer == 'Adam':
            opti = optimizers.Adam(lr=self.alpha)
            self.q_network.compile(loss=loss_func, optimizer = opti)


class DQNAgent(QNAgent):
    
    """Class implementing DQN.
        
        This is a basic outline of the functions/parameters you will need
        in order to implement the DQNAgnet. This is just to get you
        started. You may need to tweak the parameters, add new ones, etc.
        
        Feel free to change the functions and funciton parameters that the
        class provides.
        
        We have provided docstrings to go along with our suggested API.
        
        Parameters
        ----------
        q_network: keras.models.Model
        Your Q-network model.
        preprocessor: deeprl_hw2.core.Preprocessor
        The preprocessor class. See the associated classes for more
        details.
        memory: deeprl_hw2.core.Memory
        Your replay memory.
        gamma: float
        Discount factor.
        target_update_freq: float
        Frequency to update the target network. You can either provide a
        number representing a soft target update (see utils.py) or a
        hard target update (see utils.py and Atari paper.)
        num_burn_in: int
        Before you begin updating the Q-network your replay memory has
        to be filled up with some number of samples. This number says
        how many.
        train_freq: int
        How often you actually update your Q-Network. Sometimes
        stability is improved if you collect a couple samples for your
        replay memory, for every Q-network update that you run.
        batch_size: int
        How many samples in each minibatch.
        """
    def __init__(self,
                 network_type,
                 num_actions,
                 preprocessors,
                 memory,
                 burnin_policy,
                 observing_policy,
                 training_policy,
                 testing_policy,
                 gamma=GAMMA,
                 alpha=ALPHA,
                 target_update_freq=TARGET_QNET_RESET_INTERVAL,
                 num_burn_in=SAMPLES_BURN_IN,
                 train_freq=TRAINING_FREQUENCY,
                 eval_freq=EVALUATION_FREQUENCY,
                 batch_size=BATCH_SIZE):
        
        QNAgent.__init__(self,network_type,num_actions,preprocessors,memory,burnin_policy,observing_policy,training_policy,testing_policy,gamma,alpha,target_update_freq,num_burn_in,train_freq,eval_freq,batch_size)
        
        
        if network_type=='LINEAR':
            self.qt_network  	= self.create_linear_model(window = WINDOW, \
                                                           input_shape = (IMG_ROWS, IMG_COLS), \
                                                           num_actions = self.num_actions, \
                                                           )
                
            self.q_network   	= self.create_linear_model(window = WINDOW, \
                                                                                                           input_shape = (IMG_ROWS, IMG_COLS), \
                                                                                                           num_actions = self.num_actions
                                                                                                           )
        elif network_type=='DEEP':
            
            self.qt_network  	= self.create_deep_model(window = WINDOW, \
                                                         input_shape = (IMG_ROWS, IMG_COLS), \
                                                         num_actions = self.num_actions
                                                         )
                
            self.q_network   	= self.create_deep_model(window = WINDOW, \
                                                                                                     input_shape = (IMG_ROWS, IMG_COLS), \
                                                                                                     num_actions = self.num_actions
                                                                                                     )

    def compile(self, optimizer, loss_func):
        """Setup all of the TF graph variables/ops.
            
            This is inspired by the compile method on the
            keras.models.Model class.
            
            This is a good place to create the target network, setup your
            loss function and any placeholders you might need.
            
            You should use the mean_huber_loss function as your
            loss_function. You can also experiment with MSE and other
            losses.
            
            The optimizer can be whatever class you want. We used the
            keras.optimizers.Optimizer class. Specifically the Adam
            optimizer.
            """
            
        if optimizer == 'Adam':
        	opti = optimizers.Adam(lr=self.alpha)
        	self.q_network.compile(loss=loss_func, optimizer = opti)
        
    def update_policy(self):
        """Update your policy.
            
            Behavior may differ based on what stage of training your
            in. If you're in training mode then you should check if you
            should update your network parameters based on the current
            step and the value you set for train_freq.
            
            Inside, you'll want to sample a minibatch, calculate the
            target values, update your network, and then update your
            target values.
            
            You might want to return the loss and other metrics as an
            output. They can help you monitor how training is going.
            """
        
        if self.num_samples % self.train_freq == 0:
            
            # generate batch samples for CNN
            mem_samples = self.memory.sample(self.batch_size)
            mem_samples = self.atari_proc.process_batch(mem_samples)
            input_state_batch=np.zeros((self.batch_size, 4, 84, 84))
            input_nextstate_batch=np.zeros((self.batch_size, 4, 84, 84))
            input_mask_batch=np.zeros((self.batch_size,self.num_actions))
            output_target_batch=np.zeros((self.batch_size,self.num_actions))
            
            for ind in range(self.batch_size):
                input_state_batch[ind,:,:,:] = mem_samples[ind].state
                input_nextstate_batch[ind,:,:,:] = mem_samples[ind].next_state
                input_mask_batch[ind, mem_samples[ind].action] = 1
            
            target_q = self.q_network.predict([input_nextstate_batch, self.input_dummymask_batch],batch_size=1)
            best_target_q = np.amax(target_q, axis=1)
            #print 'best Q values of batch'
            #print best_target_q
            for ind in range(self.batch_size):
                output_target_batch[ind, mem_samples[ind].action] = mem_samples[ind].reward + self.gamma*best_target_q[ind]
        
            temp_loss = self.q_network.train_on_batch(x=[input_state_batch, input_mask_batch], y=output_target_batch)
            
	if self.num_updates % (self.target_update_freq/100) == 0:
            self.train_loss.append(temp_loss)
	    self.mean_q.append(self.eval_avg_q())

	if self.num_updates % self.target_update_freq == 0:
	    self.save_data()
	    print "======================= Sync target and source network ============================="
	    tfrl.utils.get_hard_target_model_updates(self.qt_network, self.q_network)
            

    def save_data(self):
        
        plt.plot(self.mean_q)
        plt.savefig('dqn_mean_q_{0}.jpg'.format(self.network_type))
        plt.close()
        plt.plot(self.train_loss)
        plt.savefig('dqn_train_loss_{0}.jpg'.format(self.network_type))
        plt.close()
        with open('dqn_mean_q_{0}.data'.format(self.network_type),'w') as f:
            pickle.dump(self.mean_q,f)
        with open('dqn_train_loss_{0}.data'.format(self.network_type),'w') as f:
            pickle.dump(self.train_loss,f)
            self.q_network.save_weights('dqn_source_{0}.weight'.format(self.network_type))


class DuelingDQNAgent(QNAgent):
    
    """Class implementing DQN.
        
        This is a basic outline of the functions/parameters you will need
        in order to implement the DQNAgnet. This is just to get you
        started. You may need to tweak the parameters, add new ones, etc.
        
        Feel free to change the functions and funciton parameters that the
        class provides.
        
        We have provided docstrings to go along with our suggested API.
        
        Parameters
        ----------
        q_network: keras.models.Model
        Your Q-network model.
        preprocessor: deeprl_hw2.core.Preprocessor
        The preprocessor class. See the associated classes for more
        details.
        memory: deeprl_hw2.core.Memory
        Your replay memory.
        gamma: float
        Discount factor.
        target_update_freq: float
        Frequency to update the target network. You can either provide a
        number representing a soft target update (see utils.py) or a
        hard target update (see utils.py and Atari paper.)
        num_burn_in: int
        Before you begin updating the Q-network your replay memory has
        to be filled up with some number of samples. This number says
        how many.
        train_freq: int
        How often you actually update your Q-Network. Sometimes
        stability is improved if you collect a couple samples for your
        replay memory, for every Q-network update that you run.
        batch_size: int
        How many samples in each minibatch.
        """
    def __init__(self,
                 network_type,
                 num_actions,
                 preprocessors,
                 memory,
                 burnin_policy,
                 observing_policy,
                 training_policy,
                 testing_policy,
                 gamma=GAMMA,
                 alpha=ALPHA,
                 target_update_freq=TARGET_QNET_RESET_INTERVAL,
                 num_burn_in=SAMPLES_BURN_IN,
                 train_freq=TRAINING_FREQUENCY,
                 eval_freq=EVALUATION_FREQUENCY,
                 batch_size=BATCH_SIZE):

        QNAgent.__init__(self,network_type,num_actions,preprocessors,memory,burnin_policy,observing_policy,training_policy,testing_policy,gamma,alpha,target_update_freq,num_burn_in,train_freq,eval_freq,batch_size)

        if network_type=='LINEAR':
	      self.qt_network  	= self.create_linear_model(window = WINDOW, \
							input_shape = (IMG_ROWS, IMG_COLS), \
							num_actions = self.num_actions)
    
	      self.q_network   	= self.create_linear_model(window = WINDOW, \
						    input_shape = (IMG_ROWS, IMG_COLS), \
						    num_actions = self.num_actions)
        elif network_type=='DEEP':
                              
	      self.qt_network  	= self.create_dueling_model(window = WINDOW, \
						   input_shape = (IMG_ROWS, IMG_COLS), \
						   num_actions = self.num_actions)
                              
	      self.q_network   	= self.create_dueling_model(window = WINDOW, \
						   input_shape = (IMG_ROWS, IMG_COLS), \
						   num_actions = self.num_actions)

	      #self.qt_network.load_weights('ftdqn_target_DEEP.weight')
	      #self.q_network.load_weights('ftdqn_source_DEEP.weight')

    def compile(self, optimizer, loss_func):
        """Setup all of the TF graph variables/ops.
        
            This is inspired by the compile method on the
            keras.models.Model class.
        
            This is a good place to create the target network, setup your
            loss function and any placeholders you might need.
        
            You should use the mean_huber_loss function as your
            loss_function. You can also experiment with MSE and other
            losses.
        
            The optimizer can be whatever class you want. We used the
            keras.optimizers.Optimizer class. Specifically the Adam
            optimizer.
        """
            
        if optimizer == 'Adam':
            opti = optimizers.Adam(lr=self.alpha)
            self.q_network.compile(loss=loss_func, optimizer = opti)

    def update_policy(self):
        """Update your policy.
            
            Behavior may differ based on what stage of training your
            in. If you're in training mode then you should check if you
            should update your network parameters based on the current
            step and the value you set for train_freq.
            
            Inside, you'll want to sample a minibatch, calculate the
            target values, update your network, and then update your
            target values.
            
            You might want to return the loss and other metrics as an
            output. They can help you monitor how training is going.
        """
                
        # generate batch samples for CNN
        mem_samples = self.memory.sample(self.batch_size)
        mem_samples = self.atari_proc.process_batch(mem_samples)
        input_state_batch=np.zeros((self.batch_size, 4, 84, 84))
        input_nextstate_batch=np.zeros((self.batch_size, 4, 84, 84))
        input_mask_batch=np.zeros((self.batch_size,self.num_actions))
        output_target_batch=np.zeros((self.batch_size,self.num_actions))
        
        for ind in range(self.batch_size):
            input_state_batch[ind,:,:,:] = mem_samples[ind].state
            input_nextstate_batch[ind,:,:,:] = mem_samples[ind].next_state
            input_mask_batch[ind, mem_samples[ind].action] = 1
        
        aux_q = self.q_network.predict([input_nextstate_batch, self.input_dummymask_batch],batch_size=self.batch_size)
        best_actions=np.argmax(aux_q,axis=1)
        target_q = self.qt_network.predict([input_nextstate_batch, self.input_dummymask_batch],batch_size=self.batch_size)
        best_target_q = target_q[range(self.batch_size), best_actions]
	if DEBUG:
        	print 'best Q values of batch {0}'.format(best_target_q)
        for ind in range(self.batch_size):
            output_target_batch[ind, mem_samples[ind].action] = mem_samples[ind].reward + self.gamma*best_target_q[ind]
        
        temp_loss = self.q_network.train_on_batch(x=[input_state_batch, input_mask_batch], y=output_target_batch)

    
	if self.num_updates % (self.target_update_freq/100) == 0:
            self.train_loss.append(temp_loss)
	    self.mean_q.append(self.eval_avg_q())

	if self.num_updates % self.target_update_freq == 0:
	    self.save_data()
	    print "======================= Sync target and source network ============================="
	    tfrl.utils.get_hard_target_model_updates(self.qt_network, self.q_network)


        
    def save_data(self):
	exp_num = 1
        plt.plot(self.mean_q)
        plt.savefig('dueling_mean_q_{0}_{1}.jpg'.format(self.network_type, exp_num))
        plt.close()
        plt.plot(self.train_loss)
        plt.savefig('dueling_train_loss_{0}_{1}.jpg'.format(self.network_type, exp_num))
        plt.close()
        #with open('ftdqn_mean_q_{0}_{1}.data'.format(self.network_type, exp_num),'w') as f:
        #    pickle.dump(self.mean_q,f)
        #with open('ftdqn_train_loss_{0}_{1}.data'.format(self.network_type, exp_num),'w') as f:
        #    pickle.dump(self.train_loss,f)
        #self.q_network.save_weights('ftdqn_source_{0}_{1}.weight'.format(self.network_type, exp_num))
        #self.qt_network.save_weights('ftdqn_target_{0}_{1}.weight'.format(self.network_type, exp_num))
