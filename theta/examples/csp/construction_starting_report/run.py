#!/usr/bin/env python
# -*- coding: utf-8 -*-

import sys, os, json
from tqdm import tqdm
import random
from copy import deepcopy
from functools import partial

script_path = os.path.abspath(os.path.dirname(os.path.realpath(__file__)))
print(f"script_path: {script_path}")

# -------------------- Theta --------------------
# pip install -U theta

from theta.utils import DictObject
from theta.nlp.runner import run_training, run_evaluating, run_predicting

from theta.nlp.entity_extraction import TaskLabels, TaggedData, TaskTag
from theta.nlp.entity_extraction import TaskDataset, Model, Evaluator
from theta.nlp.entity_extraction.utils import split_text_tags
# 实体标签
entity_labels = [
    '工程编号', '项目名称（ID）', '监理单位', '施工单位', '开工时间', '计划开工时间', '计划竣工日期'
]
task_labels = TaskLabels(entity_labels=entity_labels, )

# -------------------- Global Variables --------------------
TASK_NAME = "entity_extraction"

#  bert_model_path = os.path.realpath(f"{script_path}/pretrained/bert-base-chinese")
bert_model_path = "/opt/local/pretrained/bert-base-chinese"
print("bert_model_path:", bert_model_path)

data_path = os.path.realpath(f"{script_path}/data")
print("data_path:", data_path)

seed = 42
learning_rate = 2e-5
batch_size = 8
max_length = 512
do_split = False
min_best = 0.9
earlystopping_patience = 10

args = DictObject(**dict(
    task_name=TASK_NAME,
    task_labels=task_labels,
    bert_model_path=bert_model_path,
    extract_threshold=0,
    debug=False,
    seed=seed,
    max_length=max_length,
    local_rank=-1,
    # 是否将文本划分为多个短句
    do_split=do_split,
    # Training
    batch_size=batch_size,
    learning_rate=learning_rate,
    num_training_epochs=500,
    max_training_episodes=100,
    min_best=min_best,
    # Early Stopping
    earlystopping_monitor="best_f1",
    earlystopping_patience=earlystopping_patience,
    earlystopping_mode="max",
    # Predicting
    repeat=1,
    # Data files
    train_file=None,
    val_file=None,
    test_file=None,
    best_model_file="best_model.pt",
    eval_on_training=True,
    # outputs
    output_dir="./outputs",
    log_dir="./logs",
))

random.seed(seed)


# -------------------- tag_text() --------------------
def tag_text(idx, line):
    """
    由原始文本行生成返回标准的TaggedData标注对象

    # 实体抽取任务标注样本数据结构
    @dataclass
    class TaggedData:
        idx: str = ""
        text: str = ""
        tags: List[TaskTag] = field(default_factory=list)
        metadata: Any = None  # 应用侧自行定义的附加标注信息

    # 实体标注结构
    @dataclass
    class EntityTag:
        c: str = None  # category: 实体类别
        s: int = -1  # start: 文本片断的起始位置
        m: str = None  # mention: 文本片断内容

    """

    json_data = json.loads(line)

    idx = json_data['id']
    text = json_data['text']
    line_tags = json_data['tags']

    tags = []
    for tag in line_tags:
        #  print("tag:", tag)
        tag = TaskTag().from_json(tag)
        # # (e_c, e_s, e_m)
        # tag = TaskTag(c=e_c, s=e_s, m=e_m)

        tags.append(tag)

    tags = sorted(tags, key=lambda x: x.start)

    #  print("idx:", idx, "text:", text, "tags:", tags)
    return TaggedData(idx, text, tags, None)


# -------------------- build_final_result() --------------------
def build_final_result(tagged_text, decoded_tags):
    """
    根据预测结果构造生成应用需要的输出格式（对应一行原始文本）

    tagged_text: TaggedData # tag_text()函数生成的 TaggedData 标注对象
    decoded_tags: List[TaskTag] # decode_text_tags()函数返回的解码后的标注对象列表，通常是TaskTag对象列表，对象结构见tag_text()函数。

    """

    idx, text = tagged_text.idx, tagged_text.text
    # true_tags, metadata = tagged_text.tags, tagged_text.metadata

    entities_list = []
    for tag in decoded_tags:
        e_c, e_s, e_m = tag.category, tag.start, tag.mention
        entity = (e_c, e_s, e_m)

        entities_list.append(entity)

    result = {"ID": idx, "text": text, "entities": entities_list}

    return result


# -------------------- decode_text_tags() --------------------


def decode_text_tags(pred_tags):
    """
    模型预测出来的 TaskTag 对象，根据实际需要，可以在这里做解码变换，要求返回相同结构的TaskTag对象。
    无需解码时，直接返回pred_tags。
    """

    decoded_tags = pred_tags

    return decoded_tags


# -------------------- predict_test_file() --------------------
"""
"""


def predict_test_file(args, tokenizer, results_file="results.json"):
    test_file = args.test_file
    best_model_file = args.best_model_file

    test_data = [x for x in test_data_generator(test_file)]

    # [(full_tags, sent_tags_list)]
    predictions = run_predicting(args, Model, Evaluator, test_data,
                                 best_model_file, tokenizer)

    def decode_predictions(predictions):
        decoded_tags_list = []

        for pred_tags in predictions:
            decoded_tags = decode_text_tags(pred_tags)
            decoded_tags_list.append(decoded_tags)

        return decoded_tags_list

    decoded_tags_list = decode_predictions(predictions)
    assert len(test_data) == len(decoded_tags_list)

    predictions_file = "./predictions.json"
    with open(predictions_file, "w") as wt:
        for tagged_text, tags in zip(test_data, decoded_tags_list):
            # idx, text, true_tags = tagged_text.idx, tagged_text.text
            # true_tags, metadata = tagged_text.tags, tagged_text.metadata
            # pred = {
            #     "idx": idx,
            #     "text": text,
            #     "tags": [tag.to_json() for tag in tags],
            # }
            # line = f"{json.dumps(pred, ensure_ascii=False)}\n"
            pred_tagged_text = deepcopy(tagged_text)
            pred_tagged_text.tags = tags
            line = pred_tagged_text.to_json()
            wt.write(f"{line}\n")
    print(f"Saved {len(decoded_tags_list)} lines in {predictions_file}")

    final_tags_list = []
    for tagged_text, decoded_tags in zip(test_data, decoded_tags_list):
        final_tags = build_final_result(tagged_text, decoded_tags)
        final_tags_list.append(final_tags)

    with open(results_file, "w") as wt:
        for d in final_tags:
            line = json.dumps(d, ensure_ascii=False)
            wt.write(f"{line}\n")
    print(f"Saved {len(final_tags_list)} results in {results_file}")

    return final_tags_list


# -------------------- Train Data --------------------
def data_generator(data_file, do_split=False):
    lines = open(data_file).readlines()
    for idx, line in enumerate(tqdm(lines, desc=os.path.basename(data_file))):
        line = line.strip()

        #  print("line:", line)
        tagged_text = tag_text(idx, line)
        if idx < 5 or idx > len(lines) - 5:
            print(tagged_text)

        if args.do_split:
            text, tags, others = tagged_text.text, tagged_text.tags, tagged_text.others

            sentences, sent_tags_list = split_text_tags(
                tagged_text.text, tagged_text.tags)
            for sent_text, sent_tags in zip(sentences, sent_tags_list):

                if idx < 5 or idx > len(lines) - 5:
                    print(idx, sent_text, sent_tags, others)
                yield TaggedData(idx, sent_text, sent_tags, others)
        else:
            yield tagged_text


# def prepare_raw_train_data(args, data_generator, train_ratio=0.8):
#     raw_train_data = [d for d in data_generator(args.train_file)]
#     raw_train_data = random.sample(raw_train_data, len(raw_train_data))
#     num_train_samples = int(len(raw_train_data) * train_ratio)

#     return raw_train_data, num_train_samples

# raw_train_data, num_train_samples = prepare_raw_train_data(args, data_generator, train_ratio=0.8)


def train_data_generator(train_file):
    raw_train_data = [d for d in data_generator(args.train_file)]
    raw_train_data = random.sample(raw_train_data, len(raw_train_data))
    # for data in raw_train_data[:num_train_samples]:
    for data in raw_train_data:
        yield data


def val_data_generator(val_file):
    raw_val_data = [d for d in data_generator(args.val_file)]
    for data in raw_val_data:
        # for data in raw_train_data[num_train_samples:]:
        # for data in raw_train_data:
        yield data


def test_data_generator(test_file):
    for data in data_generator(test_file):
        yield data


def do_train(args, tokenizer):
    print(f"----- load train_dataset")
    partial_train_data_generator = partial(train_data_generator,
                                           train_file=args.train_file)
    train_dataset = TaskDataset(args, partial_train_data_generator, tokenizer)

    print(f"----- load val_dataset")
    partial_val_data_generator = partial(val_data_generator,
                                         val_file=args.val_file)
    val_dataset = TaskDataset(args, partial_val_data_generator, tokenizer)

    print(f"----- run_training()")
    run_training(args, Model, Evaluator, train_dataset, val_dataset)


def do_eval(args, tokenizer):
    partial_val_data_generator = partial(val_data_generator,
                                         val_file=args.val_file)
    val_dataset = TaskDataset(args, Model, Evaluator,
                              partial_val_data_generator, tokenizer)

    run_evaluating(args, val_dataset)


def do_predict(args, tokenizer):
    if args.best_model_file is None:
        args.best_model_file = "best_model.pt"

    predict_test_file(args, tokenizer)


# -------------------- Main --------------------
def main(args):
    from functools import partial
    from theta.nlp import get_default_tokenizer

    dict_path = f"{args.bert_model_path}/vocab.txt"
    print(f"dict_path: {dict_path}")
    tokenizer = get_default_tokenizer(dict_path)

    if args.do_train:
        do_train(args, tokenizer)

    if args.do_eval:
        do_eval(args, tokenizer)

    if args.do_predict:
        do_predict(args, tokenizer)


# -------------------- Arguments --------------------
def get_args():
    import argparse

    parser = argparse.ArgumentParser()

    # -------------------- Commands --------------------
    parser.add_argument("--do_train",
                        action="store_true",
                        help="Whether to run training.")
    parser.add_argument("--do_eval",
                        action="store_true",
                        help="Whether to run evaluating.")
    parser.add_argument("--do_predict",
                        action="store_true",
                        help="Whether to run predicting.")

    # -------------------- Auto arguments --------------------
    for k, v in args.items():
        parser.add_argument(f"--{k}", default=v, help=k.replace('_', ' '))

    cmd_args, unknown_args = parser.parse_known_args()

    os.makedirs(cmd_args.output_dir, exist_ok=True)

    if unknown_args:
        print("unknown_args:", unknown_args)

    return cmd_args, unknown_args


if __name__ == "__main__":
    cmd_args, _ = get_args()
    args.update(**cmd_args.__dict__)
    main(args)