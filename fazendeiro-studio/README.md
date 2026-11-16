# Fazendeiro Studio

Estúdio local em Python para um fazendeiro fictício de IA: três pautas diárias, prompts para Flow, orçamento manual de créditos, importação de vídeo, Whisper, FFmpeg, aprovação humana e métricas.

**Estado:** primeira versão local. Não conecta ao Google Flow, não controla o navegador, não compra créditos e não publica no TikTok. A geração no Flow e a publicação são manuais. Nenhuma senha, cookie ou chave de conta é necessária.

## Iniciar no computador

Requer Python 3.11+, FFmpeg com libass/libx264 e uma fonte como DejaVu Sans. Instale FFmpeg pelo gerenciador de pacotes do seu sistema. No Windows, deixe `ffmpeg` e `ffprobe` no PATH.

```sh
python -m venv .venv
# Linux/macOS:
.venv/bin/python -m pip install -e '.[test]'
.venv/bin/python -m farmstudio.cli serve
# Windows PowerShell, no lugar dos dois comandos acima:
# .venv\Scripts\python -m pip install -e ".[test]"
# .venv\Scripts\python -m farmstudio.cli serve
```

Abra `http://127.0.0.1:8765`. O servidor usa apenas loopback, um processo e um trabalhador de mídia; não deve ser exposto diretamente à internet. O projeto não inclui autenticação para acesso remoto. No celular, a interface pode ser usada se houver uma implantação privada autenticada apropriada; essa implantação não está incluída.

No primeiro uso, o Whisper baixa um modelo gratuito do Hugging Face. Isso consome rede e espaço local, sem consumir créditos do Flow. O padrão `tiny` favorece leveza; sotaques e ruído exigem revisão. O código pode usar `base` ou `small` para melhor reconhecimento, ao custo de memória e tempo. A dependência de PyAV foi fixada após um teste detectar incompatibilidade com a versão 19.

## Um vídeo do começo ao fim

1. Clique em **Preparar as três ideias de hoje**. Repetir o clique não cria pautas extras para a mesma data.
2. Abra uma produção. No Flow, anexe a imagem-base fornecida pelo proprietário ou use o mesmo Character salvo. Confira **Omni Flash 1.1, 720p, 9:16, 10s, UMA saída, 15 créditos**.
3. Marque a conferência de custo e reserve uma tentativa no livro local. Isso **não** dispara o Flow. Gere uma saída e reconcilie a tentativa como cobrada, incerta ou reembolsada. Uma falha não prova reembolso.
4. Baixe o clipe com voz e importe no painel. O sprint aceita 10s com tolerância de 0,5s, até 4K e 200 MB. O arquivo é renomeado; sua origem e hash são guardados.
5. Transcreva com Whisper, confira as palavras e os tempos, salve a revisão. As legendas podem ser editadas em JSON. Tempos fora do vídeo, invertidos ou sobrepostos são rejeitados.
6. Opcionalmente importe música ou efeito sonoro com registro de licença, origem e condições de uso. Não há download automático de músicas nem presunção de que um áudio gratuito seja licenciado. O efeito entra aos 2s; escolha um som que faça sentido naquele momento.
7. Renderize. O FFmpeg exporta H.264/AAC em 1080×1920, 30fps e 10s; normaliza voz, insere legendas e identificação de IA. A resolução é um upscale do clipe 720p, sem recuperar detalhe inexistente. O zoom discreto usa a margem para manter toda a imagem original visível. Música e efeitos entram em volume baixo e ainda precisam de conferência auditiva.
8. Assista ao resultado completo e marque a checklist. A aprovação fica vinculada ao SHA-256 do arquivo. Mudanças nos insumos ou legendas invalidam aprovação e renderização anteriores.
9. Publique manualmente, com a identificação de conteúdo gerado por IA do TikTok ativada. Copie a descrição e registre o link real do vídeo. Registrar um link não envia nenhum arquivo.
10. Registre métricas acumuladas em momentos comparáveis (por exemplo, 2h, 24h e 48h). O ranking considera o último snapshot de cada vídeo e prioriza seguidores por mil views, depois compartilhamentos por mil views. Isso é um sinal exploratório, não previsão de viralização.

## Automação diária e limites

Enquanto o servidor estiver ligado, o agendador prepara o lote do dia depois das 06h em `America/Fortaleza`. Se ligado após esse horário, prepara no próximo ciclo de até 30s. Desligado, não executa. Alternativa para agendador do sistema:

```sh
.venv/bin/python -m farmstudio.cli daily --data data
.venv/bin/python -m farmstudio.cli status --data data
```

O banco contém **21 roteiros originais previamente escritos**, suficientes para o sprint de sete dias. O sistema distribui três ainda não usados por dia; os temas com sinais melhores podem ocupar dois espaços, preservando exploração quando possível. Não existe geração ilimitada por LLM nesta versão. Quando os roteiros acabam, para com mensagem explícita em vez de repetir. Acrescente novos objetos com IDs únicos em `farmstudio/ideas.json` e revise-os antes da execução seguinte.

O livro local usa transações SQLite para bloquear reservas acima de **45 créditos por dia**, incluindo tentativas incertas. Usa ID idempotente por tentativa e aceita apenas uma saída de 15 créditos. **Não vê o saldo da conta Google e não impede gastos feitos diretamente no Flow fora do livro.** Se uma regeneração consumir os créditos de um dos três espaços diários, reduza as publicações do dia; não ultrapasse o limite.

Segundo a documentação Google consultada em 16/11/2026, o Omni Flash 1.1 será retirado em 05/12/2026. As reservas param nessa data. Trocar nome ou preço no código sem reconferir a documentação não é uma migração válida. Não existe fallback automático para outro modelo, API paga ou resolução.

## Campanha e métricas

Meta de trabalho: 10.000 seguidores totais e 100.000 visualizações em sete dias; ponto de partida informado: 250 seguidores e 2.000 visualizações históricas. Por não sabermos se essas 2.000 pertencem à janela do sprint, o painel as mantém separadas. O indicador de views soma as últimas medições dos vídeos registrados dentro da campanha, não reproduz todo o Analytics da conta. Não é uma contagem oficial de visualizações qualificadas para monetização. O total de seguidores da conta é atualizado manualmente, separado dos seguidores atribuídos aos vídeos.

O CSV usa o formato normalizado abaixo, UTF-8, delimitado por vírgulas. **Não é um importador universal do CSV bruto do TikTok Studio**: mapeie os cabeçalhos para este modelo. Troque `production_id` pelo ID em `brief.json` e use as contagens reais. Não some snapshots cumulativos entre si.

```csv
production_id,measured_at,views,followers,likes,comments,shares,average_watch_seconds,completion_rate
ID_DA_PRODUCAO,2026-11-16T18:00:00-03:00,1000,8,120,10,12,7.4,62.5
```

O importador valida todas as linhas antes de escrever, exige produção publicada e horário com fuso; uma linha inválida impede a importação inteira. Taxa de conclusão de 0 a 100; tempo médio pode superar 10s por repetições.

## Arquivos, backup e verificação

Dados ficam em `data/` (configurável por `--data` ou `FARM_DATA`). Preserve `studio.sqlite3`, possíveis arquivos WAL/SHM e as pastas de produções. Para backup simples, pare o servidor e copie toda a pasta de dados. Não há sincronização com nuvem nem retenção automática; acompanhe o espaço em disco. Nenhum arquivo de conta do TikTok ou Google deve ir para Git.

```sh
.venv/bin/python -m pytest -q
```

Os testes cobrem lotes idempotentes, concorrência do orçamento, aposentadoria do modelo, estados de aprovação, alteração do arquivo depois de aprovado, legendas inválidas, snapshots sem dupla contagem, importação CSV atômica e uma renderização real com FFmpeg e efeito sonoro sintetizado.

Veja [estratégia](docs/estrategia.md) e [integrações avaliadas](docs/integracoes.md). Entrega inicial no repositório `freiregd/tiktok`, em branch própria para revisão. As contas Google e TikTok não foram conectadas.
