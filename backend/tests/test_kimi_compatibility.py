import httpx
import pytest
from services.llm.provider import LLMClient

@pytest.mark.parametrize('base,model,expected', [
    ('https://api.kimi.ai/coding/v1','k3.1-pro',1),
    ('https://api.kimi.com/coding/v1','k3',1),
    ('https://api.kimi.ai.evil.invalid/coding/v1','k3',0),
    ('https://other.example/v1','k3',0),
])
async def test_kimi_temperature_and_reasoning_roundtrip(monkeypatch,base,model,expected):
    sent=[]
    async def post(self,url,**kwargs):
        sent.append(kwargs['json'])
        return httpx.Response(200,request=httpx.Request('POST',url),json={
            'choices':[{'message':{'content':'OK','reasoning_content':'fixture reasoning',
                                  'tool_calls':[{'id':'one','type':'function','function':{'name':'finish','arguments':'{}'}}]}}],
            'usage':{'prompt_tokens':2,'completion_tokens':3}})
    monkeypatch.setattr(httpx.AsyncClient,'post',post)
    client=LLMClient(base,'fake-key',model)
    result=await client.chat([{'role':'user','content':'fixture'}],temperature=0,max_tokens=4000)
    assert sent[0]['temperature']==expected
    assert sent[0]['max_tokens']==4000
    assert result['reasoning_content']=='fixture reasoning'
    assert result['tool_calls'][0]['id']=='one'
