# Asynchronous AudioChat
异步语音对话组件。

一般情况下，我们获得语音回复之前，是需要LLM给出完整的回复之后，再把其转换成语音。

此组件实现如下功能：
1. STT模块接收用户的语音输入，并返回转录好的文本。
2. 对LLM的输出做实时处理：若输出了完整的一句话，则把这个句子放入到一个Text queue队列中。如果LLM推理结束，则往Text queue队列中放入一个结束标志符号END。
3. TTS模块从Text queue队列中依次拿出sentence，并把其转换成音频，然后存储在一个Audio queue队列中。如果拿到结束标志符号END，则把这个符号放到Audio queue队列中。
4. Audio queue队列被不停的拿出音频，进行播放，直到拿到结束标志符号END，至此，一次语音对话完毕。

![alt text](arch/architecture.png)

## 模块设计规范
这里给出各个模块的设计标准，以便使用不同的云服务或本地服务。
### STT
```python
def stt(stt_api, *args, **kwargs) -> str:
    '''STT模块接收用户的语音输入，并返回转录好的文本。'''
    return stt_api(*args, **kwargs)
```
### LLM
```python
class LLM:
    def __init__(self, text_queue):
        '''对LLM的输出做实时处理：若输出了完整的一句话，则把这个句子放入到一个Text queue队列中。如果LLM推理结束，则往Text queue队列中放入一个结束标志符号END。'''

        self.text_queue = text_queue
    
    def _run(self, query, *args, **kwargs):
        '''LLM推理的设计规范, 强制返回一个迭代器。'''
        yield "hello"

    def _run2(self, llm_iterator):
        '''对LLM的输出做实时处理：若输出了完整的一句话，则把这个句子放入到一个Text queue队列中。如果LLM推理结束，则往Text queue队列中放入一个结束标志符号END。'''
        # 原先的代码里有一个first match函数，可以拿来做参考。
        raise "Not implemented"

    def run(self, query, *args, **kwargs) -> None:
        response_iterator = self._run(query, *args, **kwargs)

        self._run2(response_iterator)
```
### TTS
```python
class TTS:
    def __init__(self, text_queue, audio_queue):
        """从Text queue队列中依次拿出sentence，并把其转换成音频，然后存储在一个Audio queue队列中。如果拿到结束标志符号END，则把这个符号放到Audio queue队列中。"""

        self.text_queue = text_queue
        self.audio_queue = audio_queue
    
    def _run(self, text, *args, **kwargs) -> str:
        '''把text转换成语音，并保存，然后返回语音文件路径。'''
        raise
    
    def run(self, *args, **kwargs):
        raise
    
```
### Speaker
```python
class Speaker:
    def __init__(self, audio_queue):
        """Audio queue队列被不停的拿出音频，进行播放，直到拿到结束标志符号END"""

        self.audio_queue = audio_queue
    
    def _run(self, *args, **kwargs):
        raise
    
    def run(self, *args, **kwargs):
        raise
```