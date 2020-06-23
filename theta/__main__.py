#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os, glob, json
from tqdm import tqdm
from loguru import logger

all_models = []


def get_args():
    import argparse
    parser = argparse.ArgumentParser()

    parser.add_argument("--diff", action='store_true')
    parser.add_argument("--list", action='store_true')
    parser.add_argument("--show", action='store_true')
    parser.add_argument("--output_dir", default="./outputs")
    parser.add_argument("--local_id", action='append')

    args = parser.parse_args()

    return args


def find_models(args):
    output_dir = args.output_dir
    files = glob.glob(os.path.join(output_dir, "*/local_id"))

    for file in files:
        local_id = None
        with open(file, 'r') as rd:
            local_id = rd.readline().strip()
            model_path = os.path.split(file)[0]
            all_models.append((local_id, model_path))


def get_model(local_id):
    for model in all_models:
        if model[0] == local_id:
            return model
    return None


def show_model(args):
    logger.info(f"{args.local_id}")
    for model_id in args.local_id:
        model = get_model(model_id)
        args_path = os.path.join(model[1], "best/training_args.json")
        training_args = json.load(open(args_path))
        logger.warning(f"----- {model_id} -----")
        for k, v in sorted(training_args.items()):
            logger.info(f"{k}: {v}")


def list_models(args):
    print('-' * 80)
    print("local_id", ' ' * 28, "model_path")
    print('-' * 80)
    for local_id, model_path in all_models:
        print(local_id, '    ', model_path)


def diff_models(args):
    logger.info(f"{args.local_id}")
    if len(args.local_id) >= 2:
        src_model_id = args.local_id[0]
        src_model = get_model(src_model_id)
        if src_model is None:
            logger.warning(f"Model {src_model_id} not found.")
            return
        dest_model_id = args.local_id[1]
        dest_model = get_model(dest_model_id)
        if dest_model is None:
            logger.warning(f"Model {dest_model_id} not found.")
            return

        src_args_path = os.path.join(src_model[1], "best/training_args.json")
        dest_args_path = os.path.join(dest_model[1], "best/training_args.json")

        src_args = json.load(open(src_args_path))
        dest_args = json.load(open(dest_args_path))

        for k, v in sorted(src_args.items()):
            if k in dest_args and v == dest_args[k]:
                continue
            logger.debug(f"{k}, {v}")
            logger.debug(f"{k}, {dest_args.get(k, None)}")
            logger.debug('')

        for k, v in sorted(dest_args.items()):
            if k not in src_args:
                logger.debug(f"{k}, {src_args.get(k, None)}")
                logger.debug(f"{k}, {v}")
                logger.debug('')


def main(args):
    find_models(args)

    if args.list:
        list_models(args)
    elif args.diff:
        diff_models(args)
    elif args.show:
        show_model(args)
    else:
        print("Usage: theta [list|diff]")


if __name__ == '__main__':
    args = get_args()
    main(args)