# Crie um assistente de segurança com IA generativa do Amazon Bedrock e AWS

[Read in English](./README.md) | [Leer en español](./README.es.md)

O [Amazon Bedrock](https://aws.amazon.com/bedrock/) é um serviço totalmente gerenciado que oferece uma seleção de modelos básicos (FM) de alto desempenho das principais empresas de IA por meio de uma única API, junto com um amplo conjunto de recursos necessários para criar aplicativos de IA generativos, simplificando o desenvolvimento e mantendo a privacidade e a segurança. Usando o Amazon Bedrock, é possível criar um portal web de autoatendimento que permite validar se uma política do [AWS Identity and Access Management (IAM)](https://aws.amazon.com/iam/) está em conformidade com o princípio do menor privilégio, e até gerar novas políticas a partir de descrições em linguagem natural — buscando agilizar o processo de aprovação de permissões dentro de uma organização sem comprometer a segurança.

As organizações estão em constante evolução desenvolvendo novos projetos e aplicativos. Uma parte essencial da operação desses aplicativos é que eles tenham permissões e acesso para realizar ações diferentes nos serviços e recursos da AWS. Essas ações são especificadas por meio de [políticas do IAM](https://docs.aws.amazon.com/IAM/latest/UserGuide/access_policies.html), que são expressas no formato JSON.

É normal que as áreas proprietárias dos projetos solicitem permissões para a operação de seus aplicativos e que a área de segurança da organização valide, aprove ou rejeite essas solicitações. O problema surge quando as áreas do projeto solicitam acessos que não estão em conformidade com o princípio do menor privilégio. Além disso, esse problema aumenta quando as áreas de segurança não têm os detalhes do escopo desses aplicativos e devem se limitar à aplicação de boas práticas. Devido à necessidade de aprovação da permissão, a interação entre áreas de desenvolvimento e aplicativos pode se tornar um gargalo que atrasa a entrega de novos projetos e funcionalidades para a organização.

![security-flow](./images/security_flow.png)

As equipes que possuem aplicativos fazem uma ou mais interações com a área de segurança, a fim de obter os acessos que seus aplicativos exigem.

Fazer com que as solicitações de permissão estejam em conformidade com o princípio do menor privilégio desde a primeira solicitação acelera o processo de aprovação, reduz os gargalos e reduz a frustração do usuário.

## Portal de Autoatendimento Web

O aplicativo é um portal web de autoatendimento com duas funcionalidades principais:

### Analisar Política

Os usuários podem colar uma política IAM em formato JSON e receber uma análise detalhada. O Amazon Bedrock (Claude Sonnet 4.5) valida a sintaxe da política, avalia sua conformidade com o princípio do menor privilégio com base na especificidade das ações, restrição de recursos, efeitos e condições, destaca pontos de melhoria potenciais e fornece uma pontuação de conformidade em uma escala de 1 a 10. Além disso, o [IAM Access Analyzer](https://docs.aws.amazon.com/IAM/latest/UserGuide/access-analyzer-policy-validation.html) valida a política para detectar erros de sintaxe, avisos de segurança e sugestões de boas práticas.

Após a análise inicial, os usuários podem continuar a conversa — pedindo ao assistente que corrija problemas específicos, adicione condições, restrinja recursos ou gere uma versão melhorada da política.

### Gerar Política

Os usuários podem descrever as permissões que precisam em linguagem natural, e o assistente gera uma política IAM seguindo o princípio do menor privilégio. Se a solicitação for muito ampla (ex., "acesso total ao EC2"), o assistente solicita detalhes mais específicos em vez de gerar uma política insegura. Os usuários podem refinar a política através da conversa — por exemplo, pedindo para restringir a uma região específica, adicionar condições baseadas em tags ou incluir permissões adicionais.

As políticas geradas são validadas automaticamente pelo IAM Access Analyzer antes de serem entregues ao usuário.

![website](./images/security-assistant.gif)

## Arquitetura

O diagrama de arquitetura a seguir descreve como o portal de autoatendimento funciona.

![architecture_diagram](./images/architecture_diagram.png)

O portal de autoatendimento utiliza o [Amazon CloudFront](https://aws.amazon.com/cloudfront/) (1) como ponto de entrada único, servindo tanto o frontend React de um bucket do [Amazon S3](https://aws.amazon.com/s3/) (2) quanto atuando como proxy para as chamadas API ao [Amazon API Gateway](https://aws.amazon.com/api-gateway/) (3). O CloudFront adiciona um header secreto de origem às solicitações API, garantindo que apenas solicitações através do CloudFront cheguem ao backend.

O API Gateway invoca as funções [AWS Lambda](https://aws.amazon.com/lambda/) (4), que enviam a política ao [Amazon Bedrock](https://aws.amazon.com/bedrock/) (5) para análise ou geração usando Claude Sonnet 4.5, e ao [IAM Access Analyzer](https://docs.aws.amazon.com/IAM/latest/UserGuide/access-analyzer-policy-validation.html) (6) para validação verificada da política. Todas as solicitações são registradas no [Amazon DynamoDB](https://aws.amazon.com/dynamodb/) (7) para fins de auditoria.

Tanto o CloudFront quanto o API Gateway são protegidos pelo [AWS WAFv2](https://aws.amazon.com/waf/) com grupos de regras gerenciadas para reputação de IP, exploits comuns e inputs maliciosos conhecidos.

## Segurança

- O API Gateway não está exposto diretamente à internet — todo o tráfego flui através do CloudFront, que adiciona um header secreto de verificação de origem. As funções Lambda rejeitam solicitações sem este header.
- [AWS WAFv2](https://aws.amazon.com/waf/) protege tanto o CloudFront quanto o API Gateway com três grupos de regras gerenciadas da AWS: lista de reputação de IP, conjunto de regras comuns e inputs maliciosos conhecidos.
- Todo o tráfego é criptografado em trânsito (HTTPS obrigatório, TLS 1.2 mínimo).
- Os buckets S3 têm o acesso público completamente bloqueado; o acesso é apenas através do CloudFront Origin Access Control (OAC).
- Os roles de execução do Lambda seguem o princípio do menor privilégio — limitados a ARNs específicos do modelo Bedrock e da tabela DynamoDB.
- O API Gateway tem um plano de uso com limitação de taxa (10 req/s) e cota diária (1.000 solicitações).
- Todas as solicitações são registradas no DynamoDB para auditoria e no CloudWatch para observabilidade.
- O rastreamento X-Ray está habilitado no Lambda e API Gateway.

## Guia de Implementação

A solução é implantada usando [AWS CDK](https://aws.amazon.com/cdk/). Os modelos do Amazon Bedrock são [acessíveis automaticamente](https://aws.amazon.com/blogs/security/simplified-amazon-bedrock-model-access/) — nenhuma habilitação manual é necessária.

### Pré-requisitos

- Python 3.13+
- Node.js 18+
- AWS CDK CLI (`npm install -g aws-cdk`)
- AWS CLI configurado com as credenciais apropriadas

### Configuração inicial (apenas uma vez)

```bash
git clone https://github.com/aws-samples/policy-security-assistant.git
cd policy-security-assistant
npm install --prefix frontend
python -m venv cdk/.venv
source cdk/.venv/bin/activate
pip install -r cdk/requirements.txt
```

### Compilar e implantar

```bash
npm run build --prefix frontend
cdk bootstrap --app "python cdk/app.py"  # necessário apenas na primeira implantação
cdk deploy --app "python cdk/app.py"
```

A stack do CDK criará os recursos definidos na arquitetura. Quando a implantação estiver concluída, a URL do site CloudFront será exibida nos outputs. Abra o link para acessar o assistente de segurança.

Nenhuma configuração adicional é necessária — o CloudFront serve tanto o frontend quanto a API, então não há URLs de API nem chaves para configurar manualmente.

### Reimplantar após alterações

- Alterações apenas no Lambda: `cdk deploy --app "python cdk/app.py"`
- Alterações no frontend: `npm run build --prefix frontend` e depois `cdk deploy --app "python cdk/app.py"`
- Alterações na infraestrutura: `cdk diff --app "python cdk/app.py"` para visualizar, depois `cdk deploy --app "python cdk/app.py"`

## Executar Testes

```bash
pip install -r backend/requirements-test.txt
python -m pytest backend/tests/ -v
```

## Considerações de Custos

Esta solução utiliza vários serviços da AWS que podem gerar custos:

- **Amazon Bedrock** — Cobrado por token de entrada/saída. Aplica-se o preço do Claude Sonnet 4.5. Cada análise ou geração de política utiliza tipicamente entre 1.000 e 3.000 tokens. Veja [preços do Amazon Bedrock](https://aws.amazon.com/bedrock/pricing/).
- **AWS Lambda** — Cobrado por solicitação e duração de computação. O nível gratuito inclui 1 milhão de solicitações/mês.
- **Amazon DynamoDB** — Preço sob demanda para escritas do registro de auditoria. Custo mínimo para uso típico.
- **Amazon CloudFront** — Cobrado por solicitação e transferência de dados. O nível gratuito inclui 1 TB/mês.
- **AWS WAFv2** — Cobrado por web ACL, por regra e por milhão de solicitações inspecionadas.
- **IAM Access Analyzer** — As chamadas à API `ValidatePolicy` são gratuitas.

Para uma demonstração ou ferramenta interna de baixo tráfego, espere custos inferiores a $5/mês excluindo o uso do Bedrock. Os custos do Bedrock dependem do volume de análises e gerações de políticas.

## Limpeza

Para remover todos os recursos e parar de incorrer em custos:

```bash
cdk destroy --app "python cdk/app.py"
```

Isso excluirá todos os recursos criados pela stack. Observe que a tabela de auditoria do DynamoDB e o bucket de logs do S3 têm `RemovalPolicy.RETAIN` e não serão excluídos automaticamente — remova-os manualmente do console da AWS se não forem mais necessários.

## Conclusão

Usando o Amazon Bedrock e o IAM Access Analyzer, é possível criar um portal de autoatendimento para avaliar se uma política do Amazon IAM está em conformidade com o princípio do menor privilégio, e para gerar novas políticas a partir de descrições em linguagem natural. A interface conversacional permite que os usuários refinem as políticas iterativamente até que atendam aos requisitos de segurança, agilizando a interação entre a área de segurança e o desenvolvimento de aplicativos.

Além disso, é possível modificar essa solução para integrá-la ao fluxo de solicitações de permissão da sua organização, por exemplo, para rejeitar automaticamente solicitações que não atendam a uma pontuação mínima de conformidade. Isso reduzirá a lista de tarefas na área de segurança, deixando a interação humana apenas para solicitações que atendam às boas práticas.

## Observação

Esta solução é uma demonstração: A análise e geração automatizada de políticas deve ser considerada uma sugestão. Antes de implementar qualquer política em sua organização, certifique-se de validá-la com um especialista em segurança.


---

Autor: Hernan Fernandez Retamal
