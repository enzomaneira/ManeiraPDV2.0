# Auditoria e arquitetura do cardápio

## Resumo inicial da auditoria

O cardápio já tinha as entidades `MenuCategory`, `MenuItem`, `MenuOptionGroup`, `MenuOption` e tabelas many-to-many para vínculos com itens. O principal problema estava em `MenuOption`: ele armazenava nome, descrição e preço próprios, mas não possuía referência a um item real. Na exportação para a Keeta, o `itemId` era sintético (`sub-item-{id}`), o que permitia opções genéricas e duplicava a identidade do produto.

Também foram encontrados:

- `MenuItem.to_dict()` não retornava `optionGroupsId` e `availabilityId`, embora a tela dependesse desses campos.
- Rotas de atualização/exclusão de opções não filtravam o grupo pela loja do usuário.
- Preços, status e limites `minPermitted`/`maxPermitted` tinham validação incompleta.
- A edição de item podia enviar `categoryId: null` ao editar com o filtro “Todas”.
- A criação de opções não calculava `index` e a tela não tinha um fluxo explícito para selecionar um item real.
- O banco é inicializado com `create_all()` e migrações leves idempotentes, sem Alembic; portanto alterações precisam ser aditivas e tolerantes a dados legados.

## Decisões arquiteturais

1. **`MenuItem` continua sendo a entidade canônica do produto.** Um adicional, molho ou bebida é um `MenuItem` independente, com nome, descrição, preço, status, código externo e disponibilidade próprios.
2. **`MenuOption.item_id` referencia o `MenuItem` real.** O campo é nullable durante a migração para não quebrar registros antigos. Novos fluxos devem informar `itemId`; enquanto existirem opções legadas, o backend conserva os campos antigos como fallback de leitura.
3. **O preço da opção é o preço aplicado no grupo.** Quando informado, ele pode representar acréscimo/promocional no grupo; se omitido no registro legado, a serialização usa o preço do item referenciado.
4. **Um mesmo item pode aparecer em vários grupos.** O vínculo com o grupo não cria cópia do item e a chave própria de `MenuOption` preserva a configuração de seleção (`index`, `maxPermitted`, status e preço aplicado).
5. **A exportação mantém o formato de Merchant.** Os arrays `items`, `itemOffers` e `optionGroups` permanecem. Para opções novas, `optionGroups[].options[].itemId` é o ID do `MenuItem` real; opções antigas continuam sendo exportadas com o identificador legado até serem convertidas.
6. **Integridade de loja é validada na aplicação e no modelo.** Categorias, itens, grupos, opções e disponibilidades usados em uma operação precisam pertencer à loja autenticada. FKs de `store_id` foram adicionadas de forma aditiva ao modelo; a instalação existente não é destruída.
7. **Operações compostas usam uma única transação local.** A criação do item e vínculos de grupo devem ser confirmados somente ao final. A notificação à Keeta ocorre depois do commit e não desfaz o dado persistido quando a integração externa estiver indisponível.

## Migração backward-compatible

A inicialização existente adiciona, com `ADD COLUMN IF NOT EXISTS`:

- `menu_items.is_option_item`;
- `menu_options.item_id`, `index` e `status`.

Registros existentes com `item_id = NULL` continuam editáveis e exportáveis. A conversão recomendada é:

1. localizar cada opção legada pelo nome/código;
2. criar ou localizar o `MenuItem` correspondente com preço e status válidos;
3. atualizar `menu_options.item_id`;
4. revisar grupos cujo mínimo seja maior que a quantidade de opções disponíveis.

A aplicação não deve apagar ou renomear automaticamente opções legadas, pois isso poderia alterar pedidos históricos e integrações já publicadas.

## Fluxo recomendado no frontend

1. Criar o item independente: nome, descrição, preço obrigatório, status e categoria.
2. Abrir o gerenciador de grupos no item pai e criar, por exemplo, `Adicionais` com `minPermitted = 0`, `maxPermitted = 3`.
3. Selecionar itens reais existentes (`Cheddar extra`, `Bacon extra`) como opções do grupo, informando o preço aplicado.
4. Vincular o grupo ao item pai e revisar o preview.
5. Sincronizar o Merchant somente depois de validar que todos os grupos têm opções e limites possíveis.

## Exemplo completo

Itens independentes:

```json
[
  {"name": "Hambúrguer Clássico", "categoryId": 10, "price": 28.0, "status": "AVAILABLE"},
  {"name": "Cheddar extra", "categoryId": 11, "price": 4.0, "status": "AVAILABLE", "isOptionItem": true},
  {"name": "Bacon extra", "categoryId": 11, "price": 5.0, "status": "AVAILABLE", "isOptionItem": true},
  {"name": "Porção de batata", "categoryId": 12, "price": 22.0, "status": "AVAILABLE"},
  {"name": "Molho barbecue", "categoryId": 13, "price": 2.0, "status": "AVAILABLE", "isOptionItem": true},
  {"name": "Molho de alho", "categoryId": 13, "price": 2.0, "status": "AVAILABLE", "isOptionItem": true}
]
```

Grupo de adicionais (`POST /api/stores/me/option-groups`):

```json
{
  "name": "Adicionais",
  "minPermitted": 0,
  "maxPermitted": 3,
  "priceMethod": "SUM",
  "status": "AVAILABLE"
}
```

Opção apontando para item real (`POST /api/stores/me/option-groups/20/options`):

```json
{
  "itemId": 101,
  "name": "Cheddar extra",
  "description": "Fatia adicional de cheddar",
  "price": 4.0,
  "status": "AVAILABLE"
}
```

Para a porção, o grupo `Molhos` pode usar `minPermitted = 1`, `maxPermitted = 2` e opções com `itemId` dos molhos. O grupo é então vinculado com `POST /api/stores/me/menu/{itemId}/option-groups`.

## Compatibilidade e limites conhecidos

A base ainda usa migração leve no startup em vez de um histórico formal Alembic. Em uma próxima etapa operacional, recomenda-se extrair essas instruções para migrações versionadas. Até lá, não tornar `menu_options.item_id` `NOT NULL` automaticamente: isso exigiria primeiro concluir a conversão dos dados legados em produção.
