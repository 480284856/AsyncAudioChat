# -*- coding: utf-8 -*-
# https://next.api.aliyun.com/api/alimt/2018-10-12/TranslateGeneral
import os
import sys
import json
import queue

from typing import List
from threading import Thread
from alibabacloud_tea_util import models as util_models
from alibabacloud_tea_util.client import Client as UtilClient
from alibabacloud_tea_openapi import models as open_api_models
from alibabacloud_alimt20181012.models import TranslateGeneralResponse
from alibabacloud_alimt20181012 import models as alimt_20181012_models
from alibabacloud_alimt20181012.client import Client as alimt20181012Client

sys.path.append(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)
from src.AsyncAudioChat import Backend

class MT(Thread):
    def __init__(self, text):
        '''Module of Machine Translation'''
        super().__init__(daemon=True)
        self.text = text

    @staticmethod
    def create_client() -> alimt20181012Client:
        """
        使用AK&SK初始化账号Client
        @return: Client
        @throws Exception
        """
        # 工程代码泄露可能会导致 AccessKey 泄露，并威胁账号下所有资源的安全性。以下代码示例仅供参考。
        # 建议使用更安全的 STS 方式，更多鉴权访问方式请参见：https://help.aliyun.com/document_detail/378659.html。
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.json')) as F:
            args = json.load(F)
            config = open_api_models.Config(
                # 必填，请确保代码运行环境设置了环境变量 ALIBABA_CLOUD_ACCESS_KEY_ID。,
                access_key_id=args['machine_translation_key_id'],
                # 必填，请确保代码运行环境设置了环境变量 ALIBABA_CLOUD_ACCESS_KEY_SECRET。,
                access_key_secret=args['machine_translation_secret_key']
            )
        # Endpoint 请参考 https://api.aliyun.com/product/alimt
        config.endpoint = f'mt.cn-hangzhou.aliyuncs.com'
        return alimt20181012Client(config)

    def run(self):          
        self.text['text'] = self.main(self.text['text'])

    @staticmethod
    def main(
        source_text,
        *args,
        **kwargs
    ) -> None:
        client = MT.create_client()
        translate_general_request = alimt_20181012_models.TranslateGeneralRequest(
            format_type='text',
            source_language='zh',
            target_language='en',
            source_text=source_text,
            scene='general'
        )
        runtime = util_models.RuntimeOptions()
        try:
            result:TranslateGeneralResponse = client.translate_general_with_options(translate_general_request, runtime)
            return result.body.data.translated
        except Exception as error:
            # 此处仅做打印展示，请谨慎对待异常处理，在工程项目中切勿直接忽略异常。
            # 错误 message
            print(error.message)
            # 诊断地址
            print(error.data.get("Recommend"))
            UtilClient.assert_as_string(error.message)

    @staticmethod
    async def main_async(
        args: List[str],
    ) -> None:
        client = MT.create_client()
        translate_general_request = alimt_20181012_models.TranslateGeneralRequest(
            format_type='text',
            source_language='zh',
            target_language='en',
            source_text='你好',
            scene='general'
        )
        runtime = util_models.RuntimeOptions()
        try:
            # 复制代码运行请自行打印 API 的返回值
            await client.translate_general_with_options_async(translate_general_request, runtime)
        except Exception as error:
            # 此处仅做打印展示，请谨慎对待异常处理，在工程项目中切勿直接忽略异常。
            # 错误 message
            print(error.message)
            # 诊断地址
            print(error.data.get("Recommend"))
            UtilClient.assert_as_string(error.message)

class Backend(Backend):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.machine_translation_thrad = MT(text=self.text)
    
    def run(self):
        self.stt_thread.start()
        self.stt_thread.join()
        
        self.machine_translation_thrad.start()
        self.machine_translation_thrad.join()
        
        self.llm_thread.start()
        self.audio_thread.start()
        self.speaker_thread.start()

        self.llm_thread.join()
        self.audio_thread.join()
        self.speaker_thread.join()

if __name__ == '__main__':
    # print("Input: {}".format(sys.argv[1]))
    # print("Output: {}".format(MT.main(sys.argv[1], sys.argv[2:])))
    main_thread = Backend()
    main_thread.start()
    main_thread.join()