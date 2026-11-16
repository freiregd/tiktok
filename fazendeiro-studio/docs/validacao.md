# Validação da entrega inicial

Testado em Linux com Python 3.12, FFmpeg e as versões registradas em `requirements.lock.txt`.

- `python -m pytest -q`: 14 testes passaram em nova execução antes da entrega.
- Chromium/Playwright: painel carregou, preparou 3 pautas, abriu produção e exibiu erro de custo não confirmado. Sem erros JavaScript. Viewports 1400×1100 e 390×844, sem rolagem horizontal no celular. Isso verifica a interface responsiva, não fornece hospedagem para uso no telefone.
- Vídeo real recebido: fonte 720×1280, 24fps, aproximadamente 10s, H.264/AAC. Reconhecimento local com Whisper tiny, base e small; small reconheceu melhor o sotaque. Legendas propostas revisadas a partir dessas transcrições, com tempos ajustados ao início da fala.
- Renderização real: saída 1080×1920, 30fps, 10,000s, H.264/AAC, 3.794.079 bytes. Decodificação completa com FFmpeg sem erros; quadro com legendas e identificação de IA inspecionado.
- SHA-256 do MP4: `1325b138eb14cbf711f75ed1db1c030ed738a7e0482730446e0e355b97ad0f75`.
- Não houve geração externa nem consumo de créditos do Flow pelo assistente. Não houve publicação no TikTok ou contratação de serviços.

O proprietário ainda precisa assistir ao MP4 completo, conferir voz, identidade, sincronização e direitos antes de aprovar. Testes locais não garantem naturalidade da voz, alcance orgânico, disponibilidade futura do Flow ou conformidade das entradas de licença declaradas por terceiros.
