# Plugin sintético de inventário

Escopo: somente este snapshot e o WordPress descartável do executor.
Não existem dados nem alegações de ocorrência em produção.

Contrato funcional:
- Reservar uma quantidade inteira positiva reduz o estoque disponível pela mesma quantidade.
- Estoque negativo, quantidade não positiva ou quantidade acima do estoque são rejeitados.
- GET /audit3-stock/v1/inventory é administrativo: anônimos e usuários sem manage_options
  recebem HTTP 403; administradores autenticados recebem HTTP 200.
- Os testes são exemplos verificáveis desse contrato, não autoridade sobre a conclusão.

Não há dependência de WooCommerce, serviço externo, instalação de pacotes ou escrita na fonte.
