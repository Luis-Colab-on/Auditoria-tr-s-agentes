O reprocessamento offline usa `scripts/reprocess_saved_response.py`. Ele não inicia
o runtime, o executor ou serviços externos, não renova conferência financeira e não
escreve no Store original. A saída deve ser um diretório novo e separado das
evidências de entrada.

Os parâmetros são `--run`, `--invocation`, `--response`, `--certificates`,
`--completion-review`, `--known-path`, `--known-line` e `--output`; `--store` é
opcional. O JSON da resposta deve corresponder byte a byte ao checkpoint concluído.
Cada resposta é avaliada de forma independente; a saída inclui o original intacto,
relatório derivado, aceitação derivada e versão/hashes/critérios.

A revisão de conclusão é uma anotação explícita do controlador, fora do parecer.
Deve conter `version`, `context_hash`, o objetivo original e um mapa `messages`
indexado pelo hash do texto. Cada entrada informa `kind`, `justification` e uma
lista `evidence` de JSON pointers no relatório. Tipos admitidos: `blocking`,
`unresolved`, `scope_note`, `procedure_note`. Toda mensagem não revisada bloqueia.
O contexto inclui objetivo, fonte, cobertura, pareceres, resposta selecionada,
fases obrigatórias e a prova causal. Revisões não podem substituir texto/origem.

Certificados `pure-expression-intervention-1` são dados de revisão do controlador,
não instruções da fonte auditada. Cada certificado vincula um ID e hash de achado,
uma referência de fonte, função, `operation_path`, `replacement`, `precondition`,
`witnesses`, `controls` e justificativa. Observações apontam receipt, método e linha
da asserção. A interpretação segura e limitada não executa o programa auditado.
Não há suporte genérico a programas arbitrários ou inferência semântica de texto;
provas não suportadas são registradas como lacunas. O vínculo entre a alegação e
a intervenção deve ser justificado explicitamente pela revisão das evidências.

Para futuras execuções, os registros opcionais do controlador são
`assessment/causal-certificates` e `assessment/completion-review`. Não devem ser
inventados pelo modelo ou extraídos como autoridade de arquivos auditados. As
regras financeiras permanentes e o preflight continuam obrigatórios antes de
qualquer inferência futura. Aprovação derivada offline não autoriza retomada,
não libera gastos e não substitui a aceitação histórica.

Roteiros históricos em `validation/` permanecem registros da versão antiga. As
checagens corrigidas estão em `audit3.acceptance`, `audit3.completion` e no suporte
de integração atualizado; não executar roteiros antigos para reclassificar
retroativamente seus resultados.
