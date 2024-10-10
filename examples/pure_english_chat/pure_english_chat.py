# -*- coding: utf-8 -*-
# https://next.api.aliyun.com/api/alimt/2018-10-12/TranslateGeneral
import os
import sys

sys.path.append(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)
from src.AsyncAudioChat import PureEnglishChatBackend


if __name__ == '__main__':
    # print("Input: {}".format(sys.argv[1]))
    # print("Output: {}".format(MT.main(sys.argv[1], sys.argv[2:])))
    main_thread = PureEnglishChatBackend()
    main_thread.start()
    main_thread.join()