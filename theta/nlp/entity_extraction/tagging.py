#!/usr/bin/env python
# -*- coding: utf-8 -*-

from typing import List, Tuple, Dict, Any
from dataclasses import dataclass, field


@dataclass
class TaskLabels:
    """
    实体抽取任务需要的标签信息结构
    """

    # 实体类别列表
    entity_labels: List[str] = field(default_factory=list)

    def __post_init__(self):
        self.entities_label2id = {
            label: i for i, label in enumerate(self.entity_labels)
        }
        self.entities_id2label = {
            i: label for i, label in enumerate(self.entity_labels)
        }


from ..tagging import EntityTag

@dataclass
class TaskTag(EntityTag):
    """
    实体抽取任务标注结构
    """

    pass


@dataclass
class TaggedData:
    """
    实体标注样本数据结构
    """

    idx: str = ""
    text: str = ""
    tags: List[TaskTag] = field(default_factory=list)
    metadata: Any = None  # 应用侧自行定义的附加标注信息

    def to_json(self):
        return {
            'idx': self.idx,
            'text': self.text,
            'tags': [ tag.to_json() for tag in self.tags],
            'metadata': self.metadata
        }

    def from_json(self, json_data):
        self.idx = json_data['idx']
        self.text = json_data['text']
        self.tags = [ TaskTag().from_json(tag_data) for tag_data in json_data['tags']]
        self.metadata = json_data.get('metadata', None)
