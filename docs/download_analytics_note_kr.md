# 다운로드 분석 메모

PyPI 다운로드 활동은 방향성을 보는 신호이지, 신원을 식별한 사용자 수가
아닙니다. 원시 다운로드 수에는 미러, CI 시스템, 봇, 자동 의존성 해석,
캐시 갱신, 로컬 재빌드, 반복적인 환경 생성이 섞일 수 있습니다.

분석을 공개할 때는 아래 항목을 분리합니다.

- 누적 다운로드 활동
- 최근 다운로드 활동
- 추정 real-user share, 산정 방식이 있을 때만
- mirror/CI-adjusted estimate, 보정 방식이 문서화되어 있을 때만

권장 표현:

- "download activity"
- "estimated real-user share"
- "mirror/CI-adjusted estimate"
- "directional signal"

다운로드 수를 특정 개인 수, 유료 계정 수, 조직 단위 사용, 배포된 시스템
수로 바꾸어 말하지 않습니다. PyPI 분석 이미지를 사용한다면 measurement
artifact로 표시합니다. 그 이미지는 특정 개인, 팀, 조직이 패키지를 실행하고
있다는 증거가 아닙니다.

공개 지표에는 출처, 기간, 수집 명령 또는 artifact를 함께 둡니다. 그것이
없다면 정성적 관찰이라고 명확히 표시합니다.
