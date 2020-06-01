#!/usr/bin/env python
# -*- coding: utf-8 -*-

import numpy as np
from loguru import logger

import torch
import torch.nn as nn
from torch.nn import CrossEntropyLoss
import torch.nn.functional as F
#  from ..models.crf_0 import CRF as CRF0
#  from ..models.crf import CRF

from ..models.ncrfpp_crf import CRF as CRFPP

#  from ..models.sltk_crf import CRF as CRFSLTK

#  from TorchCRF import CRF

#  from torchcrf import CRF
# https://github.com/kmkurn/pytorch-crf/blob/master/torchcrf/__init__.py

#  from ..models.lstm_crf import CRF

#  from .models.bert_for_ner import BertCrfForNer
from .utils import CNerTokenizer, SeqEntityScore, get_entities
from ..trainer import Trainer, get_default_optimizer_parameters
from ...utils.multiprocesses import barrier_leader_process, barrier_member_processes, is_multi_processes

from torch.utils.data import DataLoader, RandomSampler, SequentialSampler
from transformers import AutoConfig, BertTokenizerFast, AutoModelForTokenClassification
from transformers.modeling_bert import BertPreTrainedModel, BertModel

CRF_TYPE = "old_crf"
CRF_TYPE = "new_crf"
CRF_TYPE = "lstm_crf"
CRF_TYPE = "TorchCRF"
CRF_TYPE = "torchcrf"
CRF_TYPE = "NCRFPP"
CRF_TYPE = "CRFSLTK"


class CRFLayer:
    def __init__(self, tagset_size, start_tag_idx, stop_tag_idx):
        self.tagset_size = tagset_size

    def get_loss(self, logits, labels, mask=None):
        raise NotImplementedError

    def decode(self, logits, mask=None):
        raise NotImplementedError


class OldCRF(CRFLayer):
    def __init__(self, tagset_size, start_tag_idx, stop_tag_idx):
        from ..models.crf_0 import CRF as CRF0
        self.crf = CRF0(tagset_size, start_tag_idx, stop_tag_idx)

    def get_loss(self, logits, labels, input_lens=None, mask=None):
        loss = self.crf.calculate_loss(logits, labels, lengths=input_lens)
        return loss

    def decode(self, logits, input_lens=None, mask=None):
        seq_path, _ = self.crf.obtain_labels(logits, input_lens)
        return seq_path


class NewCRF(CRFLayer):
    def __init__(self, tagset_size, start_tag_idx, stop_tag_idx):
        from ..models.crf import CRF
        self.crf = CRF(tagset_size, start_tag_idx, stop_tag_idx)

    def get_loss(self, logits, labels, mask=None):
        loss = self.crf(logits, labels)
        # batch_second
        #  loss = self.crf(logits.transpose(0, 1), labels.transpose(0, 1))
        return loss

    def decode(self, logits, mask=None):
        seq_path = self.crf.decode(logits, mask)
        seq_path = seq_path.cpu().numpy().tolist()[0]
        return seq_path


class NCRFPP(CRFLayer):
    def __init__(self, tagset_size, start_tag_idx, stop_tag_idx):
        from ..models.ncrfpp_crf import CRF as CRFPP
        self.crf = CRFPP(tagset_size, start_tag_idx, stop_tag_idx)

    def get_loss(self, logits, labels, mask=None):
        loss = self.crf.neg_log_likelihood_loss(logits, mask, labels)
        return loss

    def decode(self, logits, mask=None):
        scores, seq_path = self.crf._viterbi_decode(logits, mask)
        seq_path = seq_path.cpu().numpy().tolist()
        return seq_path


class CRFSLTK(CRFLayer):
    def __init__(self, tagset_size, start_tag_idx, stop_tag_idx):
        from ..models.sltk_crf import CRF as CRFSLTK
        self.crf = CRFSLTK(target_size, start_tag_idx, stop_tag_idx)

    def get_loss(self, logits, labels, mask=None):
        loss = self.crf.neg_log_likelihood_loss(logits, mask.bool(), labels)
        return loss

    def decode(self, logits, mask=None):
        _, seq_path = model.crf(logits, mask.bool())
        return seq_path


class TorchCRF(CRFLayer):
    def __init__(self, tagset_size, start_tag_idx, stop_tag_idx):
        from TorchCRF import CRF
        self.crf = CRF(tagset_size)

    def get_loss(self, logits, labels, mask=None):
        loss = self.crf(logits, labels, mask.bool())
        return loss

    def decode(self, logits, mask=None):
        seq_path = model.crf.viterbi_decode(logits, mask.bool())
        return seq_path


class PyTorchCRF(CRFLayer):
    def __init__(self, tagset_size, start_tag_idx, stop_tag_idx):
        from torchcrf import CRF
        # https://github.com/kmkurn/pytorch-crf/blob/master/torchcrf/__init__.py
        self.crf = CRF(tagset_size, batch_first=torch.BoolTensor([True]))

    def get_loss(self, logits, labels, mask=None):
        #  # preds = np.argmax(logits.cpu().detach().numpy(), axis=2)
        #  # preds = torch.argmax(logits, axis=2)
        loss = -self.crf(logits, labels)  #, mask)
        return loss

    def decode(self, logits, mask=None):
        seq_path = self.crf.decode(logits)  #, mask.bool())
        return seq_path


class LSTMCRF(CRFLayer):
    def __init__(self, tagset_size, start_tag_idx, stop_tag_idx):
        from ..models.lstm_crf import CRF
        self.crf = CRF(tagset_size, start_tag_idx, stop_tag_idx)

    def get_loss(self, logits, labels, mask=None):
        loss = self.crf.neg_log_likelihood(logits, labels)
        return loss

    def decode(self, logits, mask=None):
        seq_path = model.crf(logits)
        return seq_path


class BertCrfForNer(BertPreTrainedModel):
    def __init__(self, config):
        super(BertCrfForNer, self).__init__(config)
        #  self.num_labels = len(label2id)

        self.num_labels = config.num_labels
        self.bert = BertModel(config)
        self.dropout = nn.Dropout(config.hidden_dropout_prob)
        self.classifier = nn.Linear(config.hidden_size, self.num_labels)

        label2id = config.label2id
        start_tag_idx = label2id["[CLS]"]
        stop_tag_idx = label2id["[SEP]"]

        tagset_size = len(label2id)
        # lstm_crf
        #  self.crf = CRF(tagset_size, start_tag_idx, stop_tag_idx)
        #  self.crf = LSTMCRF(tagset_size, start_tag_idx, stop_tag_idx)

        # TorchCRF
        #  self.crf = CRF(tagset_size, start_tag_idx, stop_tag_idx)
        #  self.crf = TorchCRF(tagset_size, start_tag_idx, stop_tag_idx)

        # torchcrf
        #  self.crf = CRF(len(label2id), batch_first=torch.BoolTensor([True]))
        #  self.crf = PyTorchCRF(tagset_size, start_tag_idx, stop_tag_idx)

        # NewCRF
        #  self.crf = CRF(len(label2id), batch_first=True)
        # self.crf = NewCRF(tagset_size, start_tag_idx, stop_tag_idx)

        #  self.crf_0 = CRF0(tagset_size=len(label2id),
        #                    tag_dictionary=label2id,
        #                    device=device)
        #  self.crf_0 = CRF0(tagset_size, start_tag_idx, stop_tag_idx)
        #  self.crf = OldCRF(tagset_size, start_tag_idx, stop_tag_idx)

        # CRFPP
        self.crf = CRFPP(tagset_size, start_tag_idx, stop_tag_idx)
        #  self.crf = NCRFPP(tagset_size, start_tag_idx, stop_tag_idx)

        # CRFSLTK
        #  self.crf = CRFSLTK(target_size, start_tag_idx, stop_tag_idx)
        #  self.crf = CRFSLTK(tagset_size, start_tag_idx, stop_tag_idx)

        self.init_weights()

    def forward(self,
                input_ids,
                attention_mask=None,
                token_type_ids=None,
                labels=None,
                input_lens=None):
        outputs = self.bert(input_ids, token_type_ids, attention_mask)
        sequence_output = outputs[0]
        sequence_output = self.dropout(sequence_output)
        logits = self.classifier(sequence_output)
        outputs = (logits, )
        if labels is not None:
            loss_fct = CrossEntropyLoss()
            # Only keep active parts of the loss
            if attention_mask is not None:
                active_loss = attention_mask.view(-1) == 1
                active_logits = logits.view(-1, self.num_labels)
                active_labels = torch.where(
                    active_loss, labels.view(-1),
                    torch.tensor(loss_fct.ignore_index).type_as(labels))
                clf_loss = loss_fct(active_logits, active_labels)
            else:
                clf_loss = loss_fct(logits.view(-1, self.num_labels),
                                    labels.view(-1))

            crf_loss = clf_loss

            #  crf_loss = self.crf.get_loss(logits, labels, attention_mask)

            # lstm_crf
            #  crf_loss = self.crf.neg_log_likelihood(logits, labels)

            # TorchCRF
            #  crf_loss = self.crf(logits, labels, attention_mask.bool())

            # torchcrf
            #  # preds = np.argmax(logits.cpu().detach().numpy(), axis=2)
            #  # preds = torch.argmax(logits, axis=2)
            #  crf_loss = -self.crf(logits, labels)  #, attention_mask)

            #  crf_loss = self.crf_0.calculate_loss(logits,
            #                                       tag_list=labels,
            #                                       lengths=input_lens)

            # CRFPP
            #  crf_loss = self.crf.neg_log_likelihood_loss(
            #      logits, attention_mask, labels)

            # new local crf
            #  crf_loss = self.crf(logits, labels)
            #  crf_loss = self.crf(logits.transpose(0, 1), labels.transpose(0, 1))

            # CRFSLTK
            #  crf_loss = self.crf.neg_log_likelihood_loss(
            #      logits, attention_mask.bool(), labels)

            #  crf_loss = 0.0

            #  loss = clf_loss + crf_loss
            loss = clf_loss
            outputs = (loss, ) + outputs
        return outputs  # (loss), scores


#  from transformers import AlbertConfig
#  from transformers.modeling_albert import AlbertPreTrainedModel, AlbertModel
#
#
#  class AlbertCrfForNer(AlbertPreTrainedModel):
#      def __init__(self, config, label2id, device):
#          super(AlbertCrfForNer, self).__init__(config)
#          self.bert = AlbertModel(config)
#          self.dropout = nn.Dropout(config.hidden_dropout_prob)
#          self.classifier = nn.Linear(config.hidden_size, len(label2id))
#          self.crf = CRF(tagset_size=len(label2id),
#                         tag_dictionary=label2id,
#                         device=device,
#                         is_bert=True)
#          self.init_weights()
#
#      def forward(self,
#                  input_ids,
#                  token_type_ids=None,
#                  attention_mask=None,
#                  labels=None,
#                  input_lens=None):
#          outputs = self.bert(input_ids, token_type_ids, attention_mask)
#          sequence_output = outputs[0]
#          sequence_output = self.dropout(sequence_output)
#          logits = self.classifier(sequence_output)
#          outputs = (logits, )
#          if labels is not None:
#              loss = self.crf.calculate_loss(logits,
#                                             tag_list=labels,
#                                             lengths=input_lens)
#              outputs = (loss, ) + outputs
#          return outputs  # (loss), scores
#
#
#  from transformers import XLNetConfig
#  from transformers.modeling_xlnet import XLNetPreTrainedModel, XLNetModel
#
#
#  class XLNetCrfForNer(XLNetPreTrainedModel):
#      def __init__(self, config, label2id, device):
#          super(XLNetCrfForNer, self).__init__(config)
#          self.bert = XLNetModel(config)
#          #  self.dropout = nn.Dropout(config.hidden_dropout_prob)
#          self.dropout = nn.Dropout(0.5)
#          self.classifier = nn.Linear(config.hidden_size, len(label2id))
#          self.crf = CRF(tagset_size=len(label2id),
#                         tag_dictionary=label2id,
#                         device=device,
#                         is_bert=True)
#          self.init_weights()
#
#      def forward(self,
#                  input_ids,
#                  token_type_ids=None,
#                  attention_mask=None,
#                  labels=None,
#                  input_lens=None):
#          outputs = self.bert(input_ids, token_type_ids, attention_mask)
#          sequence_output = outputs[0]
#          sequence_output = self.dropout(sequence_output)
#          logits = self.classifier(sequence_output)
#          outputs = (logits, )
#          if labels is not None:
#              loss = self.crf.calculate_loss(logits,
#                                             tag_list=labels,
#                                             lengths=input_lens)
#              outputs = (loss, ) + outputs
#          return outputs  # (loss), scores

MODEL_CLASSES = {
    'bert': (AutoConfig, BertCrfForNer, CNerTokenizer),
    #  'bert': (AutoConfig, AutoModelForTokenClassification, CNerTokenizer),
    #  'albert': (AlbertConfig, AlbertCrfForNer, CNerTokenizer),
    #  'xlnet': (XLNetConfig, XLNetCrfForNer, CNerTokenizer),
}


def load_pretrained_tokenizer(args):
    config_class, model_class, tokenizer_class = MODEL_CLASSES[args.model_type]
    tokenizer = tokenizer_class.from_pretrained(
        args.model_path,
        do_lower_case=args.do_lower_case,
        cache_dir=args.cache_dir if args.cache_dir else None,
    )

    return tokenizer


def load_pretrained_model(args):
    # make sure only the first process in distributed training
    # will download model & vocab
    barrier_member_processes(args)

    config_class, model_class, tokenizer_class = MODEL_CLASSES[args.model_type]
    config = config_class.from_pretrained(
        args.model_path,
        cache_dir=args.cache_dir if args.cache_dir else None,
        num_labels=args.num_labels,
        label2id=args.label2id,
    )

    logger.info(f"model_path: {args.model_path}")
    logger.info(f"config:{config}")
    model = model_class.from_pretrained(
        args.model_path,
        from_tf=bool(".ckpt" in args.model_path),
        config=config,
        cache_dir=args.cache_dir if args.cache_dir else None,
    )

    # make sure only the first process in distributed training
    # will download model & vocab
    barrier_leader_process(args)

    return model


#  def load_pretrained_tokenizer(args):
#      from .trainer import load_pretrained_tokenizer as load_pretrained_tokenizer_base
#      return load_pretrained_tokenizer_base(args, MODEL_CLASSES)
#
#
#  def load_pretrained_model(args):
#      from .trainer import load_pretrained_model as load_pretrained_model_base
#      return load_pretrained_model_base(args, MODEL_CLASSES)
#


def collate_fn(batch):
    """
    batch should be a list of (sequence, target, length) tuples...
    Returns a padded tensor of sequences sorted from longest to shortest,
    """
    all_input_ids, all_attention_mask, all_token_type_ids, all_labels, all_lens = map(
        torch.stack, zip(*batch))
    max_len = max(all_lens).item()
    all_input_ids = all_input_ids[:, :max_len]
    all_attention_mask = all_attention_mask[:, :max_len]
    all_token_type_ids = all_token_type_ids[:, :max_len]
    all_labels = all_labels[:, :max_len]
    return all_input_ids, all_attention_mask, all_token_type_ids, all_labels, all_lens


def load_model(args):
    model = load_pretrained_model(args)
    model.to(args.device)
    return model


def build_default_model(args):
    """
    自定义模型
    规格要求返回模型(model)、优化器(optimizer)、调度器(scheduler)三元组。
    """

    # -------- model --------
    model = load_pretrained_model(args)
    model.to(args.device)

    # -------- optimizer --------
    from transformers.optimization import AdamW
    optimizer_parameters = get_default_optimizer_parameters(
        model, args.weight_decay)
    optimizer = AdamW(optimizer_parameters,
                      lr=args.learning_rate,
                      correct_bias=False)

    # -------- scheduler --------
    from transformers.optimization import get_linear_schedule_with_warmup

    scheduler = get_linear_schedule_with_warmup(
        optimizer,
        num_warmup_steps=args.total_steps * args.warmup_rate,
        num_training_steps=args.total_steps)

    return model, optimizer, scheduler


class NerTrainer(Trainer):
    def __init__(self, args, build_model=None, tokenizer=None):
        super(NerTrainer, self).__init__(args)
        if tokenizer:
            self.tokenizer = tokenizer
        else:
            self.tokenizer = load_pretrained_tokenizer(args)

        if build_model is None:
            self.build_model = build_default_model
        else:
            self.build_model = build_model

        self.label2id = args.label2id
        self.collate_fn = collate_fn

    def batch_to_inputs(self, args, batch, known_labels=True):
        inputs = {
            "input_ids": batch[0],
            "attention_mask": batch[1],
            "labels": batch[3] if known_labels else None,
            'input_lens': batch[4]
        }
        if args.model_type != "distilbert":
            # XLM and RoBERTa don"t use segment_ids
            inputs["token_type_ids"] = (
                batch[2] if args.model_type in ["bert", "xlnet"] else None)
        return inputs

    def examples_to_dataset(self, examples, max_seq_length):
        from .dataset import examples_to_dataset
        return examples_to_dataset(examples, self.label2id, self.tokenizer,
                                   max_seq_length)

    #  def generate_dataloader(self, args, dataset, batch_size, keep_order=True):
    #
    #      Sampler = SequentialSampler if keep_order else RandomSampler
    #      sampler = DistributedSampler(dataset) if is_multi_processes(
    #          args) else Sampler(dataset)
    #      dataloader = DataLoader(dataset,
    #                              sampler=sampler,
    #                              batch_size=batch_size,
    #                              collate_fn=collate_fn)
    #      return dataloader

    def on_eval_start(self, args, eval_dataset):
        self.metric = SeqEntityScore(args.id2label,
                                     markup=args.markup,
                                     autofix=args.autofix)

    #  def on_eval_step(self, args, eval_dataset, step, model, inputs, outputs):
    def on_eval_step(self, args, model, step, batch, batch_features):
        #  outputs = self.on_train_step(args, model, step, batch)

        inputs = self.batch_to_inputs(args, batch)
        attention_mask = inputs['attention_mask']

        outputs = model(**inputs)
        loss, logits = outputs[:2]

        #  seq_path = model.crf.decode(logits, attention_mask)

        # --------------------------------------
        # No CRF
        #  tags = np.argmax(logits.cpu(), axis=2)
        #  tags = tags.numpy().tolist()

        # --------------------------------------
        # pytorch-crf
        #  tags = model.crf.decode(logits)
        #  tags = model.crf.decode(logits.transpose(0, 1))

        # --------------------------------------
        # local CRF
        #  tags, _ = model.crf_0.obtain_labels(logits, inputs['input_lens'])

        # --------------------------------------
        # NCRFPP CRF

        if args.n_gpu > 1:
            scores, tags = model.module.crf._viterbi_decode(
                logits, inputs["attention_mask"])
        else:
            scores, tags = model.crf._viterbi_decode(logits,
                                                     inputs["attention_mask"])
        tags = tags.cpu().numpy().tolist()

        # --------------------------------------
        # local new CRF
        #  tags = model.crf.decode(logits, inputs['attention_mask'])
        #  tags = tags.cpu().numpy().tolist()[0]

        # --------------------------------------
        # torchcrf
        #  tags = model.crf.decode(logits)  #, inputs['attention_mask'].bool())

        # --------------------------------------
        # TorchCRF
        #  tags = model.crf.viterbi_decode(logits,
        #                                  inputs['attention_mask'].bool())

        # --------------------------------------
        # CRFSLTK
        #  _, tags = model.crf(logits, inputs['attention_mask'].bool())

        # --------------------------------------
        # lstm_crf
        #  tags = model.crf(logits)

        #  #  logger.debug(f"tags_0: {tags_0}")
        #  #  logger.info(f"tags_0 size: {np.array(tags_0).shape}")
        #
        #  # logits: [batch_size, seq_len, num_labels]
        #  logger.info(f"logits.shape: {logits.shape}")
        #
        #  #  logits = logits.transpose(0, 1)

        #  # tags: [batch_size, seq_len]
        #
        #  #  tags = torch.LongTensor(tags).transpose(0, 1).cpu().numpy().tolist()
        #  tags = torch.LongTensor(tags).cpu().numpy().tolist()
        #

        #  #  logger.debug(f"tags: {tags}")
        #  #  logger.info(f"tags size: {np.array(tags).shape}")

        # 评估预测结果
        out_label_ids = inputs['labels'].cpu().numpy().tolist()

        #  logger.debug(f"out_label_ids: {out_label_ids}")
        #  logger.debug(f"tags: {tags}")
        for i, label in enumerate(out_label_ids):
            temp_1 = []
            temp_2 = []
            for j, m in enumerate(label):
                if j == 0:
                    continue
                elif out_label_ids[i][j] == args.label2id['[SEP]']:
                    #  logger.info(f"temp_2: {temp_2}")
                    self.metric.update(pred_paths=[temp_2],
                                       label_paths=[temp_1])
                    break
                else:
                    temp_1.append(args.id2label[out_label_ids[i][j]])
                    temp_2.append(args.id2label[tags[i][j]])
                    #  logger.info(f"temp_2: {temp_2}")

        eval_info, _ = self.metric.result()
        results = {f'{key}': value for key, value in eval_info.items()}

        return (loss, ), results

    def on_predict_start(self, args, test_dataset):
        self.pred_results = []

    #  def on_predict_step(self, args, test_dataset, step, model, inputs,
    #                      outputs):
    def on_predict_step(self, args, model, step, batch):
        inputs = self.batch_to_inputs(args, batch, known_labels=False)
        attention_mask = inputs['attention_mask']

        outputs = model(**inputs)
        logits = outputs[0]

        #  batch_preds = model.crf.decode(logits, attention_mask)

        #  batch_preds, _ = model.crf_0._obtain_labels(logits, args.id2label,
        #                                              inputs['input_lens'])

        # ------ local CRF0
        #  batch_preds, _ = model.crf_0.obtain_labels(logits,
        #                                             inputs['input_lens'])

        # ------ local CRF
        #  batch_preds = model.crf.decode(logits, inputs['attention_mask'])
        #  batch_preds = batch_preds.cpu().numpy().tolist()[0]

        # --------------------------------------
        # torchcrf
        #  batch_preds = model.crf.decode(logits)  #, inputs['attention_mask'].bool())

        # --------------------------------------
        # TorchCRF
        #  batch_preds = model.crf.viterbi_decode(logits,
        #                                   inputs['attention_mask'].bool())

        # --------------------------------------
        # lstm_crf
        #  tags = model.crf(logits)

        # --------------------------------------
        # NCRFPP CRF
        _, batch_preds = model.crf._viterbi_decode(logits,
                                                   inputs["attention_mask"])
        batch_preds = batch_preds.cpu().numpy().tolist()

        # --------------------------------------
        # CRFSLTK
        #  _, tags = model.crf(logits, inputs['attention_mask'].bool())

        #  batch_preds = np.argmax(batch_preds, axis=2)

        #  batch_preds = model.crf.decode(logits)

        def to_entities(args, preds):
            #  logger.debug(f"{preds}")
            preds = [args.id2label[x] for x in preds]
            label_entities = get_entities(preds,
                                          args.id2label,
                                          args.markup,
                                          autofix=args.autofix)

            #  logger.debug(f"{label_entities}")
            json_d = {}
            json_d['id'] = step
            tag_seq = preds  #[args.id2label[x] for x in preds]
            json_d['tag_seq'] = " ".join(tag_seq)
            json_d['entities'] = label_entities

            #  logger.debug(f"{json_d}")

            return json_d

        #  preds = preds[0][1:-1]  # [CLS]XXXX[SEP]
        #  json_d = to_entities(args, preds)
        #  self.pred_results.append(json_d)

        for preds in batch_preds:
            preds = preds[1:-1]  # [CLS]XXXX[SEP]
            json_d = to_entities(args, preds)
            self.pred_results.append(json_d)

    def on_predict_end(self, args, test_dataset):
        return self.pred_results

    def on_eval_end(self, args, eval_dataset):
        from ...utils.ner_utils import get_ner_results
        results = get_ner_results(self.metric)
        return results