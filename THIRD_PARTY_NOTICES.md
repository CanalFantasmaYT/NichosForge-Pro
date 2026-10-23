# Third-party notices / Avisos de terceros

NichosForge Pro includes or downloads the following third-party components.
NichosForge Pro incluye o descarga los siguientes componentes de terceros.

## Bundled in this repository / Incluidos en el repositorio

| Component | Version | License | Location |
|---|---|---|---|
| [Chart.js](https://www.chartjs.org/) | 4.4.1 | MIT | `ui/vendor/chart.umd.js` |
| [YuNet face detector](https://github.com/ShiqiYu/libfacedetection.train) (OpenCV Zoo `face_detection_yunet_2023mar`) | 2023mar | BSD 3-Clause | `modelos/yunet_s_640_640.onnx` (license: `modelos/LICENSE_YuNet_BSD3.txt`) |

## Downloaded at runtime / Descargados al usarse

| Component | License | When |
|---|---|---|
| [SFace face recognizer](https://github.com/opencv/opencv_zoo/tree/main/models/face_recognition_sface) (`face_recognition_sface_2021dec.onnx`, SHA-256 verified) | Apache 2.0 | First face verification · primera verificación de rostros |
| [Inter](https://rsms.me/inter/) and [Plus Jakarta Sans](https://github.com/tokotype/PlusJakartaSans) fonts (Google Fonts) | SIL Open Font License 1.1 | Loaded by the browser · las carga el navegador |

## Python dependencies / Dependencias de Python (`requirements.txt`)

| Package | License |
|---|---|
| requests | Apache 2.0 |
| PyYAML | MIT |
| python-dotenv | BSD 3-Clause |
| openpyxl | MIT |
| anthropic | MIT |
| Pillow | MIT-CMU (HPND) |
| opencv-python-headless | Apache 2.0 (OpenCV) / MIT (wheel packaging) |
| numpy | BSD 3-Clause |

## Services / Servicios

- **YouTube Data API v3** — subject to the [YouTube API Services Terms of Service](https://developers.google.com/youtube/terms/api-services-terms-of-service).
- Optional AI providers (Google Gemini, Groq, Anthropic Claude, OpenAI, FreeLLMAPI) — subject to each provider's terms.

YouTube is a trademark of Google LLC. This project is not affiliated with, endorsed by or sponsored by YouTube or Google.
