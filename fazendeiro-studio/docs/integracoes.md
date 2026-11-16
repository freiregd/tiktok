# Integrações avaliadas em 16/11/2026

## Google Flow

- Caminho implementado: prompts em texto, uso da referência/Character na interface oficial, download oficial e importação local do MP4. O sistema não envia requisições de geração.
- A documentação de [créditos](https://support.google.com/flow/answer/16526234?hl=en) informa 15 créditos por saída de 10s no Omni Flash 1.1 720p e aposentadoria desse modelo em 05/12/2026. Configurações e custos exibidos na conta devem ser conferidos a cada uso.
- [Recursos por modelo](https://support.google.com/flow/answer/16352836?hl=en): conferir disponibilidade de referências/frames e resolução. Não assumir que outro modelo preserva os mesmos custos.
- [Projetos, Characters e downloads](https://support.google.com/flow/answer/16935308?hl=en): usar uma identidade visual/voz reaproveitável, se o recurso estiver disponível na conta. Ainda é necessário revisar as gerações.
- [Tools nativas do Flow](https://support.google.com/flow/answer/17104535?hl=en): opção oficial para explorar tarefas repetíveis dentro do próprio Flow. Disponibilidade e créditos dependem do plano; não foram configuradas nem testadas na conta do proprietário.
- Não encontramos na documentação consultada um contrato de API pública externa do Flow para controlar o app usando os créditos da assinatura. Isso não prova que nunca existirá API. Não implementamos endpoints internos, extração de cookies, evasão de CAPTCHA, automação oculta de login ou serviços de terceiros que aleguem converter Flow em API.
- Controle de navegador por um assistente só é possível com navegador compartilhado e ferramentas próprias habilitadas; abrir outra aba no celular não concede acesso. Esses controles estavam indisponíveis nesta sessão.

## Veo via API

A [API de vídeo do Gemini](https://ai.google.dev/gemini-api/docs/video) e a [tabela de preços](https://ai.google.dev/gemini-api/docs/pricing) são uma alternativa oficial de geração programática com faturamento e credenciais próprios. **Não equivalem à automação do Flow nem ao uso de seus 45 créditos.** Nenhum cliente, token ou chamada paga foi configurado. Essa alternativa só deve ser implementada depois de definir orçamento monetário separado e modelo compatível.

## TikTok

- Caminho implementado: publicação manual com checklist e registro de URL. Não há credenciais de rede social guardadas.
- [Identificação de IA](https://support.tiktok.com/en/using-tiktok/creating-videos/ai-generated-content): exigida para mídia realista gerada por IA. O projeto adiciona texto no vídeo e descrição; o operador também deve ativar a ferramenta de identificação na publicação. Uma etapa não comprova que a outra foi feita.
- [Content Posting API](https://developers.tiktok.com/doc/content-posting-api-get-started/): integração futura exige aplicativo, permissões e autorização do usuário. Restrições de clientes não auditados e revisão precisam ser verificadas antes de publicar; não há publicação automática nesta versão.
- [Música comercial](https://support.tiktok.com/en/business-and-creator/creator-and-business-accounts/commercial-use-of-music-on-tiktok): direitos da música devem ser adequados ao uso real. O projeto exige registro de licença; não verifica juridicamente o conteúdo informado.

As páginas oficiais foram consultadas para fundamentar estas decisões. Não houve acesso à conta, saldo, Studio ou termos específicos aceitos pelo proprietário.
