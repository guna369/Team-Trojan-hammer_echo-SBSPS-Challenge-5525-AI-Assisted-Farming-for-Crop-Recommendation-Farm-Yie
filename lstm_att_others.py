# Initializations
from preprocess_yield import *    # Check

model = 'lstm_att'
data_type = 'mg_cluster_weather'
from data_type_func import mg_cluster_weather  # Change
function = mg_cluster_weather # Change
#var_ts = 8   # MG, Cluster, Weather(7)
#var_concat = 1   # MG, Cluster
run_num = 1

# fix random seed for reproducibility
from numpy.random import seed 
seed(run_num)
from tensorflow import set_random_seed
set_random_seed(run_num)

import os
import numpy as np
from keras.layers import Concatenate, Dot, Input, LSTM, RepeatVector, Dense
from keras.layers import Dropout, Flatten, Reshape, Activation
from keras.optimizers import Adam
from keras.models import Model
from keras.activations import softmax
from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score
from math import sqrt
import matplotlib.pyplot as plt
import csv
import pandas as pd

os.environ["CUDA_VISIBLE_DEVICES"] = "1"  #gpu_number=2
os.environ["TF_CPP_MIN_LOG_LEVEL"] = "1"
os.environ["KERAS_BACKEND"] = "tensorflow"
 
import tensorflow as tf
config = tf.ConfigProto()
config.gpu_options.allow_growth = True
sess = tf.Session(config=config)
from keras import backend as K
K.set_session(sess)

h_s = 128   # {32, 64, 96, 128, 256}
dropout = 0.2  
batch_size = 512  
epochs = 100   # 100
lr_rate = 0.001   # (0.001, 3e-4, 5e-4)
con_dim = 2   # (1, 2, 4, 8, 16) # Reduction in dimension of the temporal context to con_dim before concat with MG, Cluster

# Create directory to save results
dir_ = 'results/%s/%s/Tx_%s_run_%s_clusters_%s_hs_%s_dim_%s_dropout_%s_bs_%s_epochs_%s_lr_%s'\
            %(data_type, model, Tx, run_num, n_clusters, h_s, con_dim, dropout, batch_size, epochs, lr_rate)

if not os.path.exists(dir_):
    os.makedirs(dir_)
    
# Data Type
x_train, x_train_mg_cluster = function(x_train, x_train_mg_cluster)
x_val, x_val_mg_cluster = function(x_val, x_val_mg_cluster)
x_test, x_test_mg_cluster = function(x_test, x_test_mg_cluster)

# Number of Variables
var_ts = x_train.shape[2]  # MG, Cluster, Weather(7)
var_concat = x_train_mg_cluster.shape[1]   # MG, Cluster

# Print shapes
print('data_train:', x_train.shape, x_train_mg_cluster.shape,\
      'y_train:', y_train.shape, 'yield_train:', yield_train.shape)
print('data_val:', x_val.shape, x_val_mg_cluster.shape,\
      'y_val:', y_val.shape, 'yield_val:', yield_val.shape)
print('data_test:', x_test.shape, x_test_mg_cluster.shape,\
      'y_test:', y_test.shape, 'yield_test:', yield_test.shape)

# Model
t_densor = Dense(1, activation = "relu")

# Softmax
def softMaxLayer(x):
    return softmax(x, axis=1)   # Use axis = 1 for attention

activator = Activation(softMaxLayer)
dotor = Dot(axes = 1)
concatenator = Concatenate(axis=-1)
flatten = Flatten()

# Temporal Attention
def temporal_one_step_attention(a):
    
    # a: Sequence of encoder hidden states (n_sample, 10, 16)
    e_temporal = t_densor(a)  # (n_samples, 10, 1)
    alphas = activator(e_temporal)    # (n_samples, 10, 1)
    t_context = dotor([alphas, a])    # (n_samples, 1, 16)
    
    return t_context, alphas, e_temporal

# Model
def model(Tx, var_ts, var_concat, h_s, dropout):
    
    # Tx : Number of input timesteps
    # var_ts: Number of input variables
    # h_s: Hidden State Dimension
    encoder_input = Input(shape = (Tx, var_ts))   # (None, 30, 9)
    mg_cluster_input = Input(shape = (var_concat, ))   # (None, 2)
    
    # Lists to store attention weights
    alphas_list = list()
    
    # Encoder LSTM, Pre-attention        
    lstm_1, state_h, state_c = LSTM(h_s, return_state=True, return_sequences=True)(encoder_input)
    lstm_1 = Dropout (dropout)(lstm_1)     # (None, 30, 32)
    
    lstm_2, state_h, state_c = LSTM(h_s, return_state=True, return_sequences=True)(lstm_1)
    lstm_2 = Dropout (dropout)(lstm_2)     # (None, 30, 32)
    
    # Temporal Attention
    t_context, alphas, e_temporal = temporal_one_step_attention (lstm_2)  # (None, 1, 32)
    t_context = flatten(t_context)  # (None, 32)
    
    # Dimension Reduction
    t_context = Dense(con_dim, activation = "relu")(t_context)   # (None, 1)
    
    # Concatenate
    context = concatenator([t_context, mg_cluster_input])   # (None, 3)
    
    # FC Layer
    yhat = Dense (1, activation = "linear")(context)   # (None, 1)
        
    # Append lists
    alphas_list.append(alphas)
    alphas_list.append(yhat)

    pred_model = Model([encoder_input, mg_cluster_input], yhat)   # Prediction Model
    prob_model = Model([encoder_input, mg_cluster_input], alphas_list)    # Weights Model
        
    return pred_model, prob_model
        
# Model Summary
pred_model, prob_model = model(Tx, var_ts, var_concat, h_s, dropout)
pred_model.summary()
    
# Train Model
pred_model.compile(loss='mean_squared_error', optimizer = Adam(lr=lr_rate)) 

hist = pred_model.fit ([x_train, x_train_mg_cluster], yield_train,
                  batch_size = batch_size,
                  epochs = epochs,
                  #callbacks = callback_lists,   # Try Early Stopping
                  verbose = 2,
                  shuffle = True,
                  validation_data=([x_val, x_val_mg_cluster], yield_val))

# Attention Weights Model
prob_model.set_weights(pred_model.get_weights())

# Plot
loss = hist.history['loss']
val_loss = hist.history['val_loss']

plt.figure()
plt.plot(loss)
plt.plot(val_loss)
plt.title('Model Loss')
plt.ylabel('Loss')
plt.xlabel('Epoch')
plt.legend(['Training Set', 'Validation Set'], loc='upper right')
plt.savefig('%s/loss_plot.png'%(dir_))
print("Saved loss plot to disk") 
plt.close()

# Save Data
loss = pd.DataFrame(loss).to_csv('%s/loss.csv'%(dir_))    # Not in original scale 
val_loss = pd.DataFrame(val_loss).to_csv('%s/val_loss.csv'%(dir_))  # Not in original scale

# Plot Ground Truth, Model Prediction
def actual_pred_plot (y_actual, y_pred, n_samples = 60):
    
    # Shape of y_actual, y_pred: (10337, 1)
    plt.figure()
    plt.plot(y_actual[ : n_samples])  # 60 examples
    plt.plot(y_pred[ : n_samples])    # 60 examples
    plt.legend(['Ground Truth', 'Model Prediction'], loc='upper right')
    plt.savefig('%s/actual_pred_plot.png'%(dir_))
    print("Saved actual vs pred plot to disk")
    plt.close()

# Correlation Scatter Plot
def scatter_plot (y_actual, y_pred):
    
    # Shape of y_actual, y_pred: (10337, 1)
    plt.figure()
    plt.scatter(y_actual[:], y_pred[:])
    plt.plot([y_actual.min(), y_actual.max()], [y_actual.min(), y_actual.max()], 'k--', lw=4)
    plt.title('Predicted Value Vs Actual Value')
    plt.ylabel('Predicted')
    plt.xlabel('Actual')
    #textstr = 'r2_score=  %.3f' %(r2_score(y_actual, y_pred))
    #plt.text(250, 450, textstr, horizontalalignment='center', verticalalignment='top', multialignment='center')
    plt.savefig('%s/scatter_plot.png'%(dir_))
    print("Saved scatter plot to disk")
    plt.close()
    
 # Evaluate Model
def evaluate_model (x_data, x_data_mg_cluster, yield_data, y_data, states_data, dataset):
    
    # x_train: (82692, 30, 9), x_train_mg_cluster: (82692, 2), yield_train: (82692, 1), y_train: (82692, 6)
    yield_data_hat = pred_model.predict([x_data, x_data_mg_cluster], batch_size = batch_size)
    yield_data_hat = scaler_y.inverse_transform(yield_data_hat)
    
    yield_data = scaler_y.inverse_transform(yield_data)
    
    metric_dict = {}  # Dictionary to save the metrics
    
    data_rmse = sqrt(mean_squared_error(yield_data, yield_data_hat))
    metric_dict ['rmse'] = data_rmse 
    print('%s RMSE: %.3f' %(dataset, data_rmse))
    
    data_mae = mean_absolute_error(yield_data, yield_data_hat)
    metric_dict ['mae'] = data_mae
    print('%s MAE: %.3f' %(dataset, data_mae))
    
    data_r2score = r2_score(yield_data, yield_data_hat)
    metric_dict ['r2_score'] = data_r2score
    print('%s r2_score: %.3f' %(dataset, data_r2score))
    
    # Save data
    y_data = np.append(y_data, yield_data_hat, axis = 1)   # (10336, 7)
    np.save("%s/y_%s" %(dir_, dataset), y_data)
    
    # Save States Data
    with open('%s/states_%s.csv' %(dir_, dataset), 'w', newline="") as csv_file:  
        wr = csv.writer(csv_file)
        wr.writerow(states_data)
       
    # Save metrics
    with open('%s/metrics_%s.csv' %(dir_, dataset), 'w', newline="") as csv_file:  
        writer = csv.writer(csv_file)
        for key, value in metric_dict.items():
            writer.writerow([key, value])
    
    # Save Actual Vs Predicted Plot and Scatter Plot for test set
    if dataset == 'test':
        actual_pred_plot (yield_data, yield_data_hat)
        scatter_plot (yield_data, yield_data_hat)
        
    return metric_dict


# Get Attention Weights
def get_temporal_weights (x_data, x_data_mg_cluster, dataset):
    
    y_data_hat_prob = prob_model.predict([x_data, x_data_mg_cluster], batch_size = batch_size)
    y_data_hat_alphas = y_data_hat_prob [0]  # first element - alphas list
    
    np.save("%s/y_%s_hat_alphas"%(dir_, dataset), y_data_hat_alphas)  # y_val_hat_alphas
    
    return y_data_hat_alphas

# Evaluate Model - Train, Validation, Test Sets
train_metrics = evaluate_model (x_train, x_train_mg_cluster, yield_train, y_train, states_train, 'train')
val_metrics = evaluate_model (x_val, x_val_mg_cluster, yield_val, y_val, states_val, 'val')
test_metrics = evaluate_model (x_test, x_test_mg_cluster, yield_test, y_test, states_test, 'test')

# Attention Weights - Train, Validation, Test Sets
y_train_hat_alphas = get_temporal_weights(x_train, x_train_mg_cluster, 'train')
y_val_hat_alphas = get_temporal_weights(x_val, x_val_mg_cluster, 'val')
y_test_hat_alphas = get_temporal_weights(x_test, x_test_mg_cluster, 'test')     