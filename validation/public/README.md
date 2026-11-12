# Resumo público da validação

Esta pasta contém somente um resumo revisado para publicação. Os registros
operacionais originais continuam preservados localmente e não fazem parte do Git.
O [resumo sanitizado](summary.json) foi derivado dos resultados existentes, sem
nova inferência, execução de testes ou alteração de pareceres.

O cenário sintético PHP/WordPress terminou com 22 checagens aprovadas sob a extensão
global explicitamente autorizada de 900 para 1.500 segundos, restrita ao julgamento
final. Foram preservados o limite de 16 chamadas, até 300 segundos por turno, os
contadores, os slots e a reprovação histórica sob o teto anterior.

O estado bruto `partial` e a conclusão revisada `completed` são resultados
distintos. A revisão local prevista classificou as notas de escopo com base nas
evidências; não editou os pareceres nem reclassificou a falha histórica. A aprovação
é restrita à fixture e aos controles demonstrados.

A [fixture pública](../../tests/fixtures/wordpress-stock/) contém a cópia dos quatro
arquivos sintéticos utilizados, inclusive o defeito intencional preservado. A
[configuração base](../php-wordpress-smoke-20261111/config.json) contém apenas
parâmetros do programa; não incorpora as exceções específicas do run.

Não são publicados confirmações financeiras factuais, identidades/fingerprints de
conta, sessões/threads/turnos do cliente oficial, login, tokens, chaves de HMAC,
registros privados, logs, dumps ou exportações ZIP operacionais. Também não se
publicam cópias integrais dos relatórios que contenham esses dados.

Este resumo não é um receipt original, não é assinado pelo serviço e não oferece
verificação pública independente da execução. Os links para evidências privadas
na documentação funcionam na instalação local; sua ausência no GitHub é deliberada.
Não fabricar evidências públicas para substituir os originais excluídos.

Código, testes, contratos, assets sintéticos, exemplos e documentação de operação
continuam disponíveis. Nenhum workflow de GitHub Actions é adicionado por esta
publicação; não há disparo automático de auditoria, inferência ou deploy.

A restrição de [nenhum gasto adicional](../../AGENTS.md) permanece obrigatória.
FAEPA e qualquer projeto real permanecem fora desta validação e publicação de
evidências.
