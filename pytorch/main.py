import os
import sys
import json
import copy
import time
import datetime
from itertools import product

import numpy as np
import torch
from torch import nn, optim

from utils.Worker import Worker
from utils.Data_Prepper import Data_Prepper
from utils.Federated_Learner import Federated_Learner
# from utils.models import LogisticRegression, MLP_LogReg, MLP_Net, CNN_Net


from torch.multiprocessing import Pool, Process, set_start_method

def init_mp():
	try:
		 set_start_method('spawn',force=True)
	except RuntimeError as e:
		print('Setting mp start method problem:', str(e))
		pass

def write_aggregate_dict(performance_dicts, filename):

	keys = ['standalone_vs_final', 'standlone_vs_rrdssgd',
			'rr_dssgd_best', 'CFFL_best_worker', 'standalone_best_worker',
			# 'sharingcontribution_vs_improvements', 'sharingcontribution_vs_final'
			 ]

	aggregate_dict = {}
	for key in keys:
		list_of_performance = [performance_dict[key] for performance_dict in performance_dicts]
		aggregate_dict[key] = np.array(list_of_performance).tolist()
		aggregate_dict[key +'_mean'] = np.mean(aggregate_dict[key], axis=0).tolist()
		aggregate_dict[key +'_std'] = np.std(aggregate_dict[key], axis=0).tolist()

		'''
		print(key, aggregate_dict[key])
		print(key +'_mean', aggregate_dict[key +'_mean'])
			# result_list.append(res)
		print(key +'_std', aggregate_dict[key +'_std'])
		'''
	with open(filename, 'w') as file:
		file.write(json.dumps(aggregate_dict))
	return


def run_experiments(args, repeat=5, logs_dir='logs'):
	update_gpu(args)

	# init steps
	model_name = str(args['model_fn']).split('.')[-1][:-2]
	subdir = "{}_p{}_e{}-{}-{}_b{}_size{}_lr{}_theta{}_{}runs_{}_a{}_{}".format(args['dataset']+'@'+args['split'],args['n_workers'], 
							args['pretrain_epochs'], args['fl_epochs'], args['fl_individual_epochs'],
							args['batch_size'], args['sample_size_cap'], args['lr'], args['theta'],
							str(repeat), args['aggregate_mode'], args['alpha'],model_name,
							)
	logdir = os.path.join(logs_dir, subdir)

	os.mkdir(logdir)


	if 'complete.txt' in os.listdir(logdir):
		return

	with open(os.path.join(logdir,'settings_dict.txt'), 'w') as file:
		[file.write(key + ' : ' + str(value) + '\n') for key,value in args.items()]

	log = open(os.path.join(logdir, 'log'), "w")
	sys.stdout = log
	print("Experimental settings are: ", args, '\n')

	performance_dicts = []
	performance_dicts_pretrain = []
	for i in range(repeat):
		print("Experiment : No.{}/{}".format(str(i+1) ,str(repeat)))
		data_prep = Data_Prepper(args['dataset'], train_batch_size=args['batch_size'], sample_size_cap=args['sample_size_cap'], train_val_split_ratio=args['train_val_split_ratio'])
		federated_learner = Federated_Learner(args, data_prep)

		# train
		federated_learner.train()
		# analyze
		federated_learner.get_fairness_analysis()

		performance_dicts.append(federated_learner.performance_dict)
		
		with open(os.path.join(logdir, 'performance_dict.log'), 'a') as log:
			log.write(json.dumps(federated_learner.performance_dict))
			log.write('\n')

		performance_dicts_pretrain.append(federated_learner.performance_dict_pretrain)
		with open(os.path.join(logdir, 'performance_dict_pretrain.log'), 'a') as log:
			log.write(json.dumps(federated_learner.performance_dict_pretrain))
			log.write('\n')


	write_aggregate_dict(performance_dicts, os.path.join(logdir, 'aggregate_dict.txt'))
	write_aggregate_dict(performance_dicts_pretrain, os.path.join(logdir, 'aggregate_dict_pretrain.txt'))

	with open(os.path.join(logdir, 'complete.txt'), 'w') as file:
		file.write('complete')
	return


from arguments import adult_args, mnist_args, names_args, update_gpu

if __name__ == '__main__':
	# init steps	
	ts = time.time()
	st = datetime.datetime.fromtimestamp(ts).strftime('%Y-%m-%d-%H:%M')
	experiment_dir = 'Experiments_{}'.format(st)
	try:
		os.mkdir(experiment_dir)
	except:
		pass
	init_mp()

	# set up arguments for experiments
	result_list = []
	args = adult_args # mnist_args
	for n_workers, sample_size_cap, fl_epochs in[[5, 2000, 100], [10, 4000, 100]]:

		args['n_workers'] = n_workers
		args['sample_size_cap'] = sample_size_cap
		args['fl_epochs'] = fl_epochs
		for theta in [0.1, 1]:
			args['theta'] = theta

			pool = Pool(processes=4)
			r = pool.apply_async(run_experiments, ((copy.deepcopy(args) ), (5), (experiment_dir)))
			result_list.append(r)
	pool.close()
	pool.join()

	for r in result_list:
		r.get()


	result_list = []
	args = adult_args # mnist_args
	for n_workers, sample_size_cap, fl_epochs in[[20, 8000, 100]]:

		args['n_workers'] = n_workers
		args['sample_size_cap'] = sample_size_cap
		args['fl_epochs'] = fl_epochs
		for theta in [0.1, 1]:
			args['theta'] = theta

			pool = Pool(processes=4)
			r = pool.apply_async(run_experiments, ((copy.deepcopy(args) ), (5), (experiment_dir)))
			result_list.append(r)
	pool.close()
	pool.join()

	for r in result_list:
		r.get()
