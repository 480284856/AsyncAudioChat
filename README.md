# Asynchronous AudioChat
异步语音对话组件。

一般情况下，我们获得语音回复之前，是需要LLM给出完整的回复之后，再把其转换成语音。

此组件实现如下功能：
1. STT模块接收用户的语音输入，并返回转录好的文本。
2. 对LLM的输出做实时处理：若输出了完整的一句话，则把这个句子放入到一个Text queue队列中。如果LLM推理结束，则往Text queue队列中放入一个结束标志符号END。
3. TTS模块从Text queue队列中依次拿出sentence，并把其转换成音频，然后存储在一个Audio queue队列中。如果拿到结束标志符号END，则把这个符号放到Audio queue队列中。
4. Audio queue队列被不停的拿出音频，进行播放，直到拿到结束标志符号END，至此，一次语音对话完毕。

![alt text](arch/architecture.png)

## 技术栈
![alt text](<arch/stack of tech.png>)

## 快速开始
首先，你需要在`src`文件夹中创建`config.json`文件并填写如下信息：
```json
{
    "lingji_key": "sk-xxx",            // 阿里云的灵积语音服务的api key                             
    "llm_url": "192.168.65.254:62707", // 模型的url，这里需要是使用Ollama部署的模型
    "model_name": "qwen2:0.5b",        // ollama中的模型的名称
    "zijie_tts_app_id": "xxx",         // 字节跳动的火山引擎的语音合成服务的app id
    "zijie_tts_access_token": "xxx"    // 字节跳动的火山引擎的语音合成服务的access token
}
```
最后，你需要使用python 3.11 来安装依赖，并运行服务：
```bash
pip install -r requirements.txt
python src/AsyncAudioChat.py
```
## 模块设计规范
这里给出各个模块的设计标准，以便使用不同的云服务或本地服务。
### STT
```python
class STT:
    def __init__(self, stt_api, *args, **kwargs):
        self.stt_api = stt_api
        self.args_for_run = args
        self.kwargs_for_run = kwargs

    def run(self):
        '''STT模块接收用户的语音输入，并保存转录好的文本。'''
        return self.stt_api(*(self.args_for_run), **(self.kwargs_for_run))
```
### InputProcessing
```python
class InputProcess:
    def __init__(self, user_input, history, *args, **kwargs):
        self.user_input = user_input
        self.history = history
    
    def run(self, *args, **kwargs):
        return self._run(*args, **kwargs)
    
    def _run(self, *args, **kwargs):
        final_input = ""
        for item in self.history:
            final_input += "User: {}\nAssistant: {}\n".format(item[0], item[1])
        return final_input + "User: {}".format(self.user_input)
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
## 语音唤醒
[![Watch the video](https://img.youtube.com/vi/2jdgFDS6OHE/maxresdefault.jpg)](https://youtu.be/2jdgFDS6OHE)
这里主要介绍本组件的语音唤醒的工作原理。
我们会使用“Main Work FLow”、“Monitor”和“Dida”三个模块来描述本组件的工作原理。
- Main Work FLow：固定回复语音对话的核心程序。
- Monitor: 用于监测是否有语音输入。
- Dida：用于计数。

这里的语音唤醒模块更像是一个闸门，其会用到STT模块，实时监测环境：
1. 如果STT模块给出的结果里含有唤醒词，那么就激活后面的工作流；
   a. 如果激活后用户没有在限定的时间内说话，则取消掉两个用于监控的线程以及主 工作流，进入休眠模式。
   b. 如果激活后用户在限定的时间内说话，则取消两个用于监控的线程，让主工作流运行。
2. 如果没有，则不激活；
![alt text](arch/architecture-voice-awake.png)

## 内容管控
[![Watch the video](https://img.youtube.com/vi/2jdgFDS6OHE/maxresdefault.jpg)](https://youtu.be/2jdgFDS6OHE)
该模块的主要作用是监测并记录用户的输入，如果用户的输入不符合规定，则进行拦截。
从技术上来说，重新实现Backend，需要在STT模块后添加一个监控模块：
- 如果用户输入不符合规定，则停止对该query进行推理，并给出默认回复。
- 如果符合规定，则继续运行后面的模块。
![alt text](arch/context_recorder.png)
