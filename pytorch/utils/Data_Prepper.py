import numpy as np
from torch.utils.data import DataLoader
from torch.utils.data.sampler import SubsetRandomSampler


class Data_Prepper:
	def __init__(self, name, train_batch_size, sample_size_cap=-1, test_batch_size=1000, valid_batch_size=None, train_val_split_ratio=0.8,device=None):
		self.name = name
		self.train_dataset, self.test_dataset = self.prepare_dataset(name)
		self.sample_size_cap = sample_size_cap
		self.train_val_split_ratio = train_val_split_ratio

		self.init_batch_size(train_batch_size, test_batch_size, valid_batch_size)

		self.init_train_valid_idx()
		self.init_valid_loader()
		self.init_test_loader()

	def init_batch_size(self, train_batch_size, test_batch_size, valid_batch_size):
		self.train_batch_size = train_batch_size
		self.test_batch_size = test_batch_size
		self.valid_batch_size = valid_batch_size if valid_batch_size else test_batch_size

	def init_train_valid_idx(self, shuffle=True):
		self.train_idx, self.valid_idx = self.get_train_valid_indices(self.train_dataset, self.train_val_split_ratio, sample_size_cap=self.sample_size_cap, shuffle=shuffle)

	def init_valid_loader(self):
		self.valid_loader = DataLoader(self.train_dataset, batch_size=self.valid_batch_size, sampler=SubsetRandomSampler(self.valid_idx), pin_memory=True)

	def init_test_loader(self):
		self.test_loader = DataLoader(self.test_dataset, batch_size=self.test_batch_size, pin_memory=True)

	def get_valid_loader(self):
		return self.valid_loader

	def get_test_loader(self):
		return self.test_loader

	def get_train_valid_indices(self, train_dataset, train_val_split_ratio, sample_size_cap=-1, shuffle=True):

		indices = list(range(  len(train_dataset) ))
		if shuffle:
			np.random.seed(1111)
			np.random.shuffle(indices)

		if sample_size_cap != -1:
			indices = indices[:min(sample_size_cap, len(train_dataset))]

		train_val_split_index = int(len(indices) * train_val_split_ratio)

		return indices[:train_val_split_index], indices[train_val_split_index:]

	def get_train_loaders(self, n_workers, split='powerlaw', batch_size=None):
		if not batch_size:
			batch_size = self.train_batch_size

		if split == 'classimbalance':
			if self.name !='mnist':
				raise NotImplementedError("Calling on dataset {}. Only dataset mnist is implemnted for this split".format(self.name))

			n_classes = len(self.train_dataset.classes)
			data_indices = [(self.train_dataset.targets == class_id).nonzero().view(-1).tolist() for class_id in range(n_classes)]
			class_sizes = np.linspace(1, n_classes, n_workers, dtype='int')
			party_mean = 600 # for mnist party_mean = 600

			from collections import defaultdict
			party_indices = defaultdict(list)
			for party_id, class_sz in enumerate(class_sizes):	
				classes = range(class_sz) # can customize classes for each party rather than just listing
				each_class_id_size = party_mean // class_sz
				for i, class_id in enumerate(classes):
					selected_indices = data_indices[class_id][:each_class_id_size]
					data_indices[class_id] = data_indices[class_id][each_class_id_size:]
					party_indices[party_id].extend(selected_indices)

					# top up to make sure all parties have the same number of samples
					if i == len(classes) - 1 and len(party_indices[party_id]) < party_mean:
						extra_needed = party_mean - len(party_indices[party_id])
						party_indices[party_id].extend(data_indices[class_id][:extra_needed])
						data_indices[class_id] = data_indices[class_id][extra_needed:]

			indices_list = [party_index_list for party_id, party_index_list in party_indices.items()] 

		elif split == 'powerlaw':
			from scipy.stats import powerlaw
			import math
			a = 1.65911332899
			party_size = int(len(self.train_idx) / n_workers)
			b = np.linspace(powerlaw.ppf(0.01, a), powerlaw.ppf(0.99, a), n_workers)
			shard_sizes = list(map(math.ceil, b/sum(b)*party_size*n_workers))
			indices_list = []
			accessed = 0
			for worker_id in range(n_workers):
				indices_list.append(self.train_idx[accessed:accessed + shard_sizes[worker_id]])
				accessed += shard_sizes[worker_id]

		elif split in ['balanced','equal']:
			from utils.utils import random_split
			indices_list = random_split(sample_indices=self.train_idx, m_bins=n_workers, equal=True)
		
		elif split == 'random':
			from utils.utils import random_split
			indices_list = random_split(sample_indices=self.train_idx, m_bins=n_workers, equal=False)

		self.indices_list = indices_list
		worker_train_loaders = [DataLoader(self.train_dataset, batch_size=batch_size, sampler=SubsetRandomSampler(indices), pin_memory=True) for indices in indices_list]

		return worker_train_loaders


	def prepare_dataset(self, name='adult'):
		if name == 'adult':
			from utils.load_adult import get_train_test
			from utils.Custom_Dataset import Custom_Dataset
			import torch

			train_data, train_target, test_data, test_target = get_train_test()

			X_train = torch.tensor(train_data.values, requires_grad=False).float()
			y_train = torch.tensor(train_target.values, requires_grad=False).long()
			X_test = torch.tensor(test_data.values, requires_grad=False).float()
			y_test = torch.tensor(test_target.values, requires_grad=False).long()

			print("X train shape: ", X_train.shape)
			print("y train shape: ", y_train.shape)
			pos, neg =(y_train==1).sum().item() , (y_train==0).sum().item()
			print("Train set Positive counts: {}".format(pos),"Negative counts: {}.".format(neg), 'Split: {:.2%} - {:.2%}'.format(1. * pos/len(X_train), 1.*neg/len(X_train)))
			print("X test shape: ", X_test.shape)
			print("y test shape: ", y_test.shape)
			pos, neg =(y_test==1).sum().item() , (y_test==0).sum().item()
			print("Test set Positive counts: {}".format(pos),"Negative counts: {}.".format(neg), 'Split: {:.2%} - {:.2%}'.format(1. * pos/len(X_test), 1.*neg/len(X_test)))

			train_set = Custom_Dataset(X_train, y_train)
			test_set = Custom_Dataset(X_test, y_test)

			return train_set, test_set
		elif name == 'mnist':
			from torchvision import datasets, transforms

			train = datasets.MNIST('datasets/', train=True, transform=transforms.Compose([
				   transforms.Pad((2,2,2,2)),
				   transforms.ToTensor(),
				   transforms.Normalize((0.1307,), (0.3081,))
							   ]))

			test = datasets.MNIST('datasets/', train=False, transform=transforms.Compose([
					transforms.Pad((2,2,2,2)),
					transforms.ToTensor(),
					transforms.Normalize((0.1307,), (0.3081,))
				]))
			return train, test

		elif name == 'names':

			from utils.load_names import get_train_test
			from utils.Custom_Dataset import Custom_Dataset
			import torch
			from collections import Counter

			X_train, y_train, X_test, y_test, reference_dict = get_train_test()

			print("X train shape: ", X_train.shape)
			print("y train shape: ", y_train.shape)
			
			print("X test shape: ", X_test.shape)
			print("y test shape: ", y_test.shape)

			'''
			train_class_counts = Counter(y_train.tolist())

			print("Train class counts: ", end='') 
			for key, value in reference_dict.items():
			    print("{} : {}, ".format(value,  train_class_counts[int(key)]), end='')
			print()
			'''

			'''
			test_class_counts = Counter(y_test.tolist())
			print("Test class counts: ", end='') 

			for key, value in reference_dict.items():
			    print("{} : {}, ".format(value,  test_class_counts[int(key)]), end='')
			print()
			print("Total of {} categories".format(len(reference_dict)))
			'''

			from utils.Custom_Dataset import Custom_Dataset
			train_set = Custom_Dataset(X_train, y_train)
			test_set = Custom_Dataset(X_test, y_test)

			return train_set, test_set

