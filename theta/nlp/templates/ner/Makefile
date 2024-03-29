TASK_NAME=ner

MAX_SEQ_LENGTH=256
DATA_ARGS=--max_length ${MAX_SEQ_LENGTH} \

PRETRAINED_MODEL=bert-base-chinese
MODEL_ARGS=--model_name_or_path=${PRETRAINED_MODEL} \

LR=2e-5
EPOCHS=10
BATCH_SIZE=16
GRADIENT_ACCUMULATION_STEPS=1
EARLYSTOPPING_PATIENCE=5
WEIGHT_DECAY=0.0
SEED=42
TRAINING_ARGS=--learning_rate ${LR} \
		--max_epochs ${EPOCHS} \
		--per_device_train_batch_size ${BATCH_SIZE} \
		--per_device_eval_batch_size ${BATCH_SIZE} \
		--gradient_accumulation_steps ${GRADIENT_ACCUMULATION_STEPS} \
		--earlystopping_patience ${EARLYSTOPPING_PATIENCE} \
		--weight_decay ${WEIGHT_DECAY} \

MONITOR=val_f1
EVAL_ARGS=--evaluation_strategy steps \
		--metric_for_best_model ${MONITOR} \
		--greater_is_better 

train:
	python run_${TASK_NAME}.py \
		--do_train \
		--task_name ${TASK_NAME} \
		${DATA_ARGS} \
		${MODEL_ARGS} \
		${TRAINING_ARGS} \
		${EVAL_ARGS} \
		--output_dir outputs \
		--overwrite_cache \
		--overwrite_output_dir \
		--fp16 \
		--seed ${SEED} \

predict:
	python run_${TASK_NAME}.py \
		--do_predict \
		--do_submit \
		--task_name ${TASK_NAME} \
		${DATA_ARGS} \
		--per_device_test_batch_size ${BATCH_SIZE} \
		--overwrite_cache \
		--fp16 \
		--seed ${SEED} \

submit:
	python run_${TASK_NAME}.py \
		--do_submit \
		--task_name ${TASK_NAME} \
		--seed ${SEED} \

eda:
	PYTHONPATH=${THETA_HOME} python -m theta.nlp.eda ${TASK_NAME}_data

webapp:
	streamlit run src/webapp.py

