"""Refresh the report memo from completed collection, inference and cloud evidence."""
import json,os,re
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'evidence/private/public-figure-expanded'
assert os.environ.get('WSL_DISTRO_NAME'),'Use WSL'
load=lambda path:json.loads(path.read_text())
collection=load(OUT/'collection.json');inference=load(OUT/'inference.json');cloud=load(ROOT/'evidence/history/public-figure-expanded-cloud.json')
assert collection['pass'] and inference['pass'] and cloud['pass'] and cloud['production_verified']
packets=load(OUT/'packets.json');people={p['key']:p for p in cloud['profiles']};sources={r['source_id']:r for r in collection['clips']}
rows=[]
for case in sorted(inference['cases'],key=lambda r:(r['person'],r['capture_day_as_published'])):
    source=sources[case['source_id']];name='트럼프' if case['person']=='public-trump' else '오바마'
    count=sum(p['case']==case['case'] for p in packets)
    rows.append(f'| {name} | {case["capture_day_as_published"]} | [DVIDS {case["source_id"]}]({case["source_url"]}) | {source["seconds"]/60:.1f}분 | {case["frames_analyzed"]} | {count} |')
raw_bytes=sum(r['declared_bytes'] for r in collection['clips']);frames=sum(r['frames_analyzed'] for r in inference['cases'])
text=f'''# 공개 인물 원본 자료 확장

트럼프는 서로 다른 원본 {people['public-trump']['source_count']}개와 관측 사진 {people['public-trump']['sampled_frames']}장, 오바마는 원본 {people['public-obama']['source_count']}개와 관측 사진 {people['public-obama']['sampled_frames']}장을 운영 서버에서 조회할 수 있다. 기존 원본 2개씩에 새로운 촬영 원본 8개씩을 추가했다. 신규 원본은 총 16개, {raw_bytes:,}바이트로 약 {raw_bytes/1e9:.2f}GB다. 각 인물의 추가 원본 8개는 촬영 날짜가 서로 다르다.

공식 공개 영상 전체를 내려받고 파일 크기, SHA256, 중복 바이트와 전체 프레임 디코딩을 확인했다. 날짜와 행사, 원본 파일을 대조했다. 원본은 Windows 작업 폴더의 비공개 자료 디렉터리에 보관한다. PythonAnywhere에는 실제 분석 사진 {cloud['observation_images']}장을 추가했다. 공개 게시글과 기존 등록 사진은 보존했다.

## 원본별 검증

| 인물 | 원본 표기 촬영일 | 원본 출처 | 전체 길이 | 실제 분석 프레임 | 추가 사진 |
| --- | --- | --- | ---: | ---: | ---: |
'''+ '\n'.join(rows)+f'''

실제 모델 분석은 선정한 구간의 총 {frames}프레임이다. 얼굴 후보 탐색으로 비교 구간을 정하고 기존 YOLOv5, Norfair와 Buffalo L로 얼굴이 사람 추적 번호에 연결되는지 확인했다. 등록 집합은 기존 인물 A, B, C와 트럼프, 오바마의 5프로필이며 candidate-2 기준을 사용했다. 연결된 후보가 있고 다른 프로필 후보와 섞이지 않은 사진을 골라 운영 이력에 저장했다. 이 자료는 시연 장면을 선정한 결과로, 프레임의 무작위 표본 정확도와 구분한다. 각 인물의 원본 수는 프레임 수나 방문 횟수와 구분한다.

날짜별 목록은 실제 분석일 기준이다. 원본 표기 촬영일은 장면 제목과 수집 기록에 보관하고 정확한 원본 촬영 시각은 미상으로 유지한다. 화면의 영상 초는 선정한 비교 영상의 재생 위치이며 원본 시작 위치는 추론 기록에 있다. 새 기록은 운영자가 얼굴 비교 화면에서 확인할 후보 상태다.

## 운영 검증

패킷 직렬화 검사 후 운영자 API로 저장했다. 원본 수와 인물별 이력을 확인하고, 각 인물의 기록 질문에서 10개 원본의 근거가 고르게 조회되는지 확인했다. 같은 패킷 재전송에서는 새 사진이 생기지 않았다. 새 관측 이미지의 무인증 접근은 거부됐다. 기존 공개 게시글은 동일했다.

수집과 모델 실행은 WSL Ubuntu 가상환경, 저장 및 조회 검사는 실제 PythonAnywhere에서 수행했다. 기존 서버와 Android API를 사용해 자료를 추가했다. 원본 파일, 장면 이미지와 등록 사진은 Git에서 제외한다. 수집한 DVIDS 페이지의 Public Domain 표기와 [이용조건](https://www.dvidshub.net/about/copyright)을 확인하고 출처 HTML을 원본과 함께 보관한다.

```bash
python tools/collect_expanded_figure_sources.py
python tools/prepare_expanded_figures.py scan
python tools/prepare_expanded_figures.py infer
python tools/populate_expanded_figures.py
python tools/document_figure_expansion.py
```

수집 증빙은 `evidence/history/public-figure-expanded-collection.json`, 실제 추론은 `public-figure-expanded-inference.json`, 운영 검증은 `public-figure-expanded-cloud.json`이다. 검토용 실제 원본 화면은 `evidence/private/public-figure-expanded/source-review.jpg`에 있다. 최초 등록과 네 구간의 검증은 [최초 시연 자료](PUBLIC_FIGURE_DEMO.md)에 보관한다.
'''
(ROOT/'docs/testing/PUBLIC_FIGURE_EXPANSION.md').write_text(text)
path=ROOT/'README.md';readme=path.read_text()
readme,n=re.subn(r'관측 사진 \d+장과 영상 실행 \d+개',f'관측 사진 {cloud["current_facts"]["sampled_frames"]}장과 영상 실행 {cloud["current_facts"]["sessions"]}개',readme,count=1);assert n==1
lines=readme.splitlines()
for i,line in enumerate(lines):
    if line.startswith('도널드 트럼프와 버락 오바마도 등록 얼굴과 발견 이력에 추가했다.'):
        lines[i]=f'공개 인물 시연 자료는 트럼프 원본 {people["public-trump"]["source_count"]}개와 관측 사진 {people["public-trump"]["sampled_frames"]}장, 오바마 원본 {people["public-obama"]["source_count"]}개와 관측 사진 {people["public-obama"]["sampled_frames"]}장이다. 추가한 서로 다른 촬영 원본 16개는 전체 파일을 수집하고 실제 모델 분석 후 운영 이력에 반영했다. 상세 원본 목록과 검증 결과는 [공개 인물 원본 자료 확장](docs/testing/PUBLIC_FIGURE_EXPANSION.md)에 있다.'
path.write_text('\n'.join(lines)+'\n')
print(json.dumps({'pass':True,'memo':'docs/testing/PUBLIC_FIGURE_EXPANSION.md','new_originals':16,'bytes':raw_bytes,'actual_inference_frames':frames}))
