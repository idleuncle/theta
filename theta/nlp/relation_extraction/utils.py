#!/usr/bin/env python
# -*- coding: utf-8 -*-

import re
import numpy as np
from collections import OrderedDict
from typing import List
from copy import deepcopy


def print_msg(msg):
    try:
        import rich
        rich.print(msg)
    except:
        print(msg)

def split_text(text, sep="。"):
    sentences = []

    text = text.replace(sep, f"\1{sep}")
    for sent in text.split(sep):
        sent = sent.replace("\1", sep)
        sentences.append(sent)

    #  assert "".join(sentences) == text, f'[{"".join(sentences)}] vs [{text}]'

    return sentences


def split_sentences(sentences, sep):
    final_sentences = []

    for sent in sentences:
        sents = split_text(sent, sep)
        final_sentences.extend(sents)

    return final_sentences


def split_text_tags(text, tags):
    from copy import deepcopy

    sentences = split_text(text, sep="。")
    sentences = split_sentences(sentences, sep="；")

    relations = [tag["predicate"] for tag in tags]
    subject_tags = [tag["subject"] for tag in tags]
    object_tags = [tag["object"] for tag in tags]

    offset = 0
    sent_tags_list = []

    for sent_text in sentences:
        sent_s = offset
        sent_e = sent_s + len(sent_text)

        sent_tags = []

        #  for tag in tags:
        #      s, p, o = tag["subject"], tag["predicate"], tag["object"]
        #
        #      s_s = s["start"]
        #      s_e = s_s + len(s["mention"])
        #      o_s = o["start"]
        #      o_e = o_s + len(o["mention"])
        #
        #      if s_s >= sent_s and s_s <= sent_e and s_e >= sent_s and s_e <= sent_e:
        #          if o_s >= sent_s and o_s <= sent_e and o_e >= sent_s and o_e <= sent_e:
        #              s = deepcopy(s)
        #              o = deepcopy(o)
        #              s["start"] -= offset
        #              o["start"] -= offset
        #              sent_tags.append({"subject": s, "predicate": p, "object": o})
        #          else:
        #              print(
        #                  f"object {o} ({o_s}, {o_e}) tag {tag} not found in {sent_text}"
        #              )
        #
        #  sent_tags = sorted(sent_tags, key=lambda x: x["subject"]["start"])

        for tag in tags:
            s, p, o = tag.s, tag.p, tag.o

            s_s = tag.s.s
            s_e = s_s + len(tag.s.m)
            o_s = tag.o.s
            o_e = o_s + len(tag.o.m)

            if s_s >= sent_s and s_s <= sent_e and s_e >= sent_s and s_e <= sent_e:
                if o_s >= sent_s and o_s <= sent_e and o_e >= sent_s and o_e <= sent_e:
                    s = deepcopy(s)
                    o = deepcopy(o)

                    s.s -= offset
                    o.s -= offset

                    sent_tags.append({"subject": s, "predicate": p, "object": o})
                else:
                    print(
                        f"object {o} ({o_s}, {o_e}) tag {tag} not found in {sent_text}"
                    )

        sent_tags = sorted(sent_tags, key=lambda x: x.s.s)

        sent_tags_list.append(sent_tags)

        offset = sent_e

    return sentences, sent_tags_list


# def split_sentences(text: str, broad_clause: bool = True) -> List[str]:
#     text = text.rstrip()
#     text = text.replace('\n', ' ')
#     if broad_clause:
#         regexes = OrderedDict({
#             'single_end_puncs': '([,，：:；;。。！？?])([^”’])',
#             'en_ellipsis': '(\\.{6})([^”’])',
#             'zh_ellipsis': '(\\…{2})([^”’])',
#             'end_puncs': '([。！？\\?][”’])([^，。！？\\?])',
#         })
#     else:
#         regexes = OrderedDict({
#             'single_end_puncs': '([,:；;。。！？?])([^”’])',
#             'en_ellipsis': '(\\.{6})([^”’])',
#             'zh_ellipsis': '(\\…{2})([^”’])',
#             'end_puncs': '([。！？\\?][”’])([^，。！？\\?])',
#         })

#     for (_, regex) in regexes.items():
#         text = re.sub(regex, r'\1\n\2', text)
#     sentences = text.rstrip().split('\n')
#     new_sentence = []
#     stop: List[int] = []
#     for i in range(len(sentences)):
#         if i in stop:
#             continue
#         if not sentences[i]:
#             continue
#         new_sentence.append(sentences[i])
#     return new_sentence


# def check_tags(text, pred_tags, true_tags):
#     pred_tags = sorted(pred_tags, key=lambda x: x['start'])
#     true_tags = sorted(true_tags, key=lambda x: x['start'])

#     identical_list = []
#     added_list = []
#     removed_list = []
#     for tag in true_tags:
#         found = np.sum([x == tag for x in pred_tags])
#         if found:
#             identical_list.append(tag)
#         else:
#             removed_list.append(tag)
#     for tag in pred_tags:
#         found = np.sum([x == tag for x in true_tags])
#         if not found:
#             added_list.append(tag)

#     diff_list = {
#         'identical': identical_list,
#         'added': added_list,
#         'removed': removed_list
#     }

#     X = len(identical_list)
#     Y = len(pred_tags)
#     Z = len(true_tags)
#     if Z > 0 and Y > 0:
#         f1, p, r = 2 * X / (Y + Z), X / Y, X / Z
#     else:
#         if Z == 0 and Y == 0:
#             f1, p, r = 1.0, 1.0, 1.0
#         else:
#             f1, p, r = 0.0, 0.0, 0.0

#     total_result = (diff_list, (X, Y, Z), (f1, p, r))

#     check_results = {
#         'total': total_result
#     }

#     return check_results


# def merge_sent_tags_list(sent_tags_list):
#     full_text = ""
#     full_tags = []

#     offset = 0
#     for sent_tags in sent_tags_list:
#         sent_text = sent_tags['text']
#         tags = sent_tags['tags']
#         full_text += sent_text
#         for tag in tags:
#             tag['start'] += offset
#             full_tags.append(tag)

#         offset += len(sent_text)

#     ret = {
#         'text': full_text,
#         'tags': full_tags
#     }
#     return ret


# def split_text_tags(sentences, full_tags):
#     offset = 0
#     sent_tags_list = []

#     for sent_text in sentences:
#         sent_s = offset
#         sent_e = sent_s + len(sent_text)

#         sent_tags = []
#         for tag in full_tags:
#             t_s = tag['start']
#             t_e = t_s + len(tag['mention'])

#             if t_s >= sent_s and t_s <= sent_e and t_e >= sent_s and t_e <= sent_e:
#                 # 标注完全包含在句子中
#                 tag = deepcopy(tag)
#                 tag['start'] -= offset
#                 sent_tags.append(tag)
#             else:
#                 """
#                 处理标注很长，跨多个句子的情况
#                 """
#                 if sent_s >= t_s and sent_s < t_e:
#                     # 句子的头部出现在标注中
#                     if sent_e >= t_s and sent_e < t_e:
#                         # 句子的尾部出现在标注中，即句子完全包含在标注中
#                         tag = deepcopy(tag)
#                         tag['start'] = 0
#                         tag['mention'] = sent_text
#                         sent_tags.append(tag)
#                     else:
#                         # 句子头在标注中，尾部在标注外，需要截断句子的头部
#                         tag = deepcopy(tag)
#                         tag['start'] = 0
#                         tag['mention'] = sent_text[:t_e - sent_s]
#                         sent_tags.append(tag)
#                 elif sent_e >= t_s and sent_e < t_e:
#                     # 句子的尾部出现在标注中
#                     if sent_s >= t_s and sent_s < t_e:
#                         # 句子的头部出现在标注中，即句子完全包含在标注中
#                         tag = deepcopy(tag)
#                         tag['start'] = 0
#                         tag['mention'] = sent_text
#                         sent_tags.append(tag)
#                     else:
#                         # 句子尾部在标注中，头部在标注外，需要截断句子的尾部
#                         tag = deepcopy(tag)
#                         tag['start'] = t_s - sent_s
#                         tag['mention'] = sent_text[t_s - sent_s:]
#                         sent_tags.append(tag)

#         #  sent_tags_list.append({
#         #      'text': sent_text,
#         #      'tags': sent_tags
#         #  })
#         sent_tags_list.append(sent_tags)

#         offset = sent_e

#     return sent_tags_list
