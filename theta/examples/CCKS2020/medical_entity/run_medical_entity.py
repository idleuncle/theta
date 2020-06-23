#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os, sys, json, random, copy
from tqdm import tqdm
from loguru import logger
from pathlib import Path
import mlflow

from theta.utils import load_json_file, split_train_eval_examples
from theta.modeling import LabeledText, load_ner_examples, load_ner_labeled_examples, save_ner_preds, show_ner_datainfo

#  if os.environ['NER_TYPE'] == 'span':
#      from theta.modeling.ner_span import load_model, get_args
#  else:
#      from theta.modeling.ner import load_model, get_args

ner_labels = ['疾病和诊断', '影像检查', '实验室检验', '手术', '药物', '解剖部位']


# -------------------- Data --------------------
def clean_text(text):
    if text:
        text = text.strip()
        #  text = re.sub('\t', ' ', text)
    return text


def train_data_generator(train_file):

    lines = load_json_file(train_file)

    for i, x in enumerate(tqdm(lines)):
        guid = str(i)
        text = clean_text(x['originalText'])
        sl = LabeledText(guid, text)

        entities = x['entities']
        for entity in entities:
            start_pos = entity['start_pos']
            end_pos = entity['end_pos'] - 1
            category = entity['label_type']
            sl.add_entity(category, start_pos, end_pos)

        yield str(i), text, None, sl.entities


def load_train_val_examples(args):
    lines = []
    for guid, text, _, entities in train_data_generator(args.train_file):
        sl = LabeledText(guid, text, entities)
        lines.append({'guid': guid, 'text': text, 'entities': entities})

    allow_overlap = args.allow_overlap
    if args.num_augements > 0:
        allow_overlap = False

    train_base_examples = load_ner_labeled_examples(
        lines,
        ner_labels,
        seg_len=args.seg_len,
        seg_backoff=args.seg_backoff,
        num_augements=args.num_augements,
        allow_overlap=allow_overlap)

    train_examples, val_examples = split_train_eval_examples(
        train_base_examples,
        train_rate=args.train_rate,
        fold=args.fold,
        shuffle=True)

    logger.info(f"Loaded {len(train_examples)} train examples, "
                f"{len(val_examples)} val examples.")
    return train_examples, val_examples


def test_data_generator(test_file):

    lines = load_json_file(test_file)
    for i, s in enumerate(tqdm(lines)):
        guid = str(i)
        text_a = clean_text(s['originalText'])

        yield guid, text_a, None, None


def load_test_examples(args):
    test_base_examples = load_ner_examples(test_data_generator,
                                           args.test_file,
                                           seg_len=args.seg_len,
                                           seg_backoff=args.seg_backoff)

    logger.info(f"Loaded {len(test_base_examples)} test examples.")
    return test_base_examples


def generate_submission(args):
    reviews_file = f"{args.latest_dir}/{args.dataset_name}_reviews_fold{args.fold}.json"
    reviews = json.load(open(reviews_file, 'r'))

    submission_file = f"{args.submissions_dir}/{args.dataset_name}_submission_{args.local_id}.json.txt"
    with open(submission_file, 'w') as wt:
        for guid, json_data in reviews.items():
            output_data = {'originalText': json_data['text'], 'entities': []}
            for json_entity in json_data['entities']:
                output_data['entities'].append({
                    'label_type':
                    json_entity['category'],
                    'overlap':
                    0,
                    'start_pos':
                    json_entity['start'],
                    'end_pos':
                    json_entity['end'] + 1
                })
            output_data['entities'] = sorted(output_data['entities'],
                                             key=lambda x: x['start_pos'])
            output_string = json.dumps(output_data, ensure_ascii=False)
            wt.write(f"{output_string}\n")

    logger.info(f"Saved {len(reviews)} lines in {submission_file}")

    from theta.modeling import archive_local_model
    archive_local_model(args, submission_file)


from theta.modeling import Params, CommonParams, NerParams, NerAppParams, log_global_params

experiment_params = NerAppParams(
    CommonParams(
        dataset_name="medical_entity",
        experiment_name="ccks2020_medical_entity",
        train_file='data/rawdata/ccks2020_2_task1_train/task1_train.txt',
        eval_file='data/rawdata/ccks2020_2_task1_train/task1_train.txt',
        test_file='data/rawdata/ccks2_task1_val/task1_no_val_utf8.txt',
        learning_rate=2e-5,
        train_max_seq_length=256,
        eval_max_seq_length=256,
        per_gpu_train_batch_size=8,
        per_gpu_eval_batch_size=8,
        per_gpu_predict_batch_size=8,
        seg_len=254,
        seg_backoff=64,
        num_train_epochs=10,
        fold=1,
        num_augements=2,
        enable_kd=True,
        enable_sda=False,
        sda_teachers=2,
        loss_type="CrossEntropyLoss",
        model_type="bert",
        model_path=
        #  "/opt/share/pretrained/pytorch/hfl/chinese-electra-large-discriminator",
        "/opt/share/pretrained/pytorch/roberta-wwm-large-ext-chinese",
        fp16=False,
        best_index="f1",
    ),
    NerParams(ner_labels=ner_labels, ner_type='span'))

experiment_params.debug()


def main(args):
    def do_eda(args):
        show_ner_datainfo(ner_labels, train_data_generator, args.train_file,
                          test_data_generator, args.test_file)

    def do_submit(args):
        generate_submission(args)

    if args.do_eda:
        do_eda(args)

    elif args.do_submit:
        do_submit(args)

    else:

        # -------------------- Model --------------------
        #  if args.ner_type == 'span':
        #      from theta.modeling.ner_span import NerTrainer
        #  else:
        #      from theta.modeling.ner import NerTrainer

        class AppTrainer(NerTrainer):
            def __init__(self, args, ner_labels):
                super(AppTrainer, self).__init__(args,
                                                 ner_labels,
                                                 build_model=None)

            #  def on_predict_end(self, args, test_dataset):
            #      super(Trainer, self).on_predict_end(args, test_dataset)

        trainer = AppTrainer(args, ner_labels)

        def do_train(args):
            train_examples, val_examples = load_train_val_examples(args)
            trainer.train(args, train_examples, val_examples)

        def do_eval(args):
            args.model_path = args.best_model_path
            _, eval_examples = load_train_val_examples(args)
            model = load_model(args)
            trainer.evaluate(args, model, eval_examples)

        def do_predict(args):
            args.model_path = args.best_model_path
            test_examples = load_test_examples(args)
            model = load_model(args)
            trainer.predict(args, model, test_examples)
            reviews_file, category_mentions_file = save_ner_preds(
                args, trainer.pred_results, test_examples)
            return reviews_file, category_mentions_file

        if args.do_train:
            do_train(args)

        elif args.do_eval:
            do_eval(args)

        elif args.do_predict:
            do_predict(args)

        elif args.do_experiment:
            if args.tracking_uri:
                mlflow.set_tracking_uri(args.tracking_uri)
            mlflow.set_experiment(args.experiment_name)

            with mlflow.start_run(run_name=f"{args.local_id}") as mlrun:
                log_global_params(args, experiment_params)

                # ----- Train -----
                do_train(args)

                # ----- Predict -----
                do_predict(args)

                # ----- Submit -----
                do_submit(args)


if __name__ == '__main__':

    def add_special_args(parser):
        return parser

    if experiment_params.ner_params.ner_type == 'span':
        from theta.modeling.ner_span import load_model, get_args, NerTrainer
    else:
        from theta.modeling.ner import load_model, get_args, NerTrainer

    args = get_args(experiment_params=experiment_params,
                    special_args=[add_special_args])
    logger.info(f"args: {args}")

    main(args)