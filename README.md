# Agenda de Licitações

Sistema web para a **intranet da secretaria** que organiza a agenda de sessões de licitação,
com controle de acesso por perfil de usuário e trilha de auditoria.

## Funcionalidades

- **Painel**: só aparecem os quadros que têm conteúdo. Cada usuário escolhe as **colunas, a ordem delas e o critério de
  ordenação** (também clicando no título da coluna). O quadro **Licitações em andamento**
  reúne editais publicados, remarcadas e sessões abertas, inclusive as suspensas depois de
  abertas para análise documental; as suspensas antes da abertura ficam em quadro próprio.
  O **número do edital** (PE 007/2026, CE 075/2025…) é o destaque de cada
  linha, e as linhas têm **cores suaves por modalidade** (pregão eletrônico em verde,
  pregão presencial em vermelho, concorrência eletrônica em azul etc.). Cada linha mostra
  a equipe (pregoeiro/agente e os dois membros; o terceiro só aparece se escalado).
  Mostra sessões de hoje, todas as próximas sessões (sem limite de prazo, pois há
  editais publicados com mais de 30 dias de antecedência), suspensas sem data definida,
  credenciamentos abertos com alerta de renovação, totais por situação e sessões que já
  passaram sem desfecho registrado.
- **Calendário mensal** com as sessões coloridas pela situação.
- **Cadastro de licitações**: nº do processo e do edital, modalidade (Lei nº 14.133/2021),
  objeto, publicação do edital, data/hora da sessão, local/plataforma, equipe, valor
  estimado, situação e observações.
- **Credenciamento**: fica aberto por tempo indeterminado, sem sessão; tem vigência anual
  (padrão: 1 ano após a publicação) renovada pelo botão “Renovar por 1 ano”. Só admite as
  situações “Em andamento” e “Concluída”.
- **Equipe**: pregoeiro ou agente de contratação e mais dois membros, além de um terceiro
  membro opcional, escolhidos no cadastro de **servidores** (com vínculo funcional). O sistema **impede salvar uma equipe
  com minoria de efetivos** (maioria estrita de efetivos ou empregados públicos do quadro
  permanente: 2 de 3, ou 3 de 4 com o terceiro membro) e exige a equipe completa fora da fase de planejamento (exceto
  inexigibilidade).
- **Férias e afastamentos**: registrados por servidor. O sistema impede escalar quem
  estará afastado na data da sessão; se a sessão **já estiver em andamento**, avisa e
  permite **trocar ou manter** o membro (a decisão vai para o histórico). O sistema alerta
  na licitação quando um afastamento lançado depois atinge uma equipe já escalada.
- **Suspender / remarcar**, conforme a fase da sessão pública:
  - antes da abertura: *suspensa sem data definida*, *remarcada* ou *remarcada após
    retificação do edital*;
  - com a sessão aberta (em andamento): *suspensa para análise documental* ou
    *remarcada pelo pregoeiro (continuação)* em outro dia.
  Todas exigem data e hora e ficam no histórico.
- **WhatsApp em imagem**: gera imagens no formato de tela de celular (1080 × 1920) com as
  licitações abertas ou em andamento — número do edital, modalidade, data e horário,
  objeto e equipe —, nas cores da modalidade. O sistema escolhe o layout mais compacto que
  ainda mantém a leitura (nenhum texto abaixo de 26 px) para caber o maior número de
  licitações numa só imagem; se não couberem, divide em imagens equilibradas. Também
  há imagem individual por licitação e, se preferir, o mesmo conteúdo em texto.
- **Busca e filtros** por texto, modalidade, situação, responsável e período.
- **Exportação .ics** da agenda (filtrada) para Outlook, Google Agenda, Thunderbird etc.
- **Histórico** de alterações em cada licitação e **auditoria** geral (logins, cadastros,
  alterações, exclusões, gestão de usuários).
- **Gestão de usuários**: cadastro, troca de perfil, desativação e redefinição de senha.
  Senhas temporárias precisam ser trocadas no primeiro acesso.

## Perfis de acesso

Perfis: **Administrador**, **Gestor**, **Pregoeiro / Agente de Contratação** e **Consulta**.
O que cada perfil pode fazer é definido pelo Administrador em **Configurações → Permissões
dos perfis** (o Administrador sempre tem tudo). Padrão inicial:

| Permissão                                   | Administrador | Gestor | Pregoeiro / Agente | Consulta |
|---------------------------------------------|:-:|:-:|:-:|:-:|
| Ver painel, calendário e licitações         | ✔ | ✔ | ✔ | ✔ |
| Cadastrar e editar licitações               | ✔ | ✔ | ✔ |   |
| Suspender e remarcar sessões                | ✔ | ✔ | ✔ |   |
| Excluir licitações                          | ✔ | ✔ |   |   |
| Cadastrar servidores                        | ✔ | ✔ |   |   |
| Registrar férias e afastamentos             | ✔ | ✔ |   |   |
| Consultar auditoria                         | ✔ | ✔ |   |   |
| Alterar parâmetros (órgão, modalidades, situações) | ✔ | ✔ |   |   |
| Gerenciar usuários                          | ✔ |   |   |   |

## Feriados, pontos facultativos e prazo mínimo legal

- Já vêm cadastrados os feriados **nacionais**, o **estadual do RJ** (São Jorge, 23/04 — Lei
  estadual 5.198/2008) e os **municipais de Três Rios** (São Sebastião, 20/01, e Emancipação,
  14/12, normalmente transferida por decreto — registre a transferência a cada ano). Terça de
  Carnaval e Dia do Servidor estão como feriado; Carnaval (segunda), Quarta de Cinzas e
  Corpus Christi, como pontos facultativos. Confira a lista com a legislação local e ajuste em **Configurações →
  Feriados e pontos facultativos**.
- É possível cadastrar feriados ou pontos facultativos (fixos, móveis pela Páscoa ou numa data
  específica) e **transferir a data** de um feriado num ano (ex.: decreto municipal que
  antecipa o feriado), registrando o ato. Ao cadastrar ou transferir, o sistema avisa se já
  há sessão marcada no dia.
- A data da sessão (no cadastro, na edição e nas remarcações) **não pode cair em sábado,
  domingo ou feriado**; em ponto facultativo, só com a confirmação de que haverá expediente.
- **Prazo mínimo legal** (art. 55 da Lei 14.133/2021; dispensa: art. 75, § 3º; diálogo
  competitivo: art. 32, § 1º, I): cada licitação informa o **critério de
  julgamento**, e as opções dependem da modalidade (ex.: pregão para bens — 8 dias úteis — ou
  serviços comuns — 10; concorrência com técnica e preço — 35). As opções de cada modalidade
  são configuráveis. A contagem começa no dia útil seguinte à divulgação (art. 183, § 1º, I)
  e a sessão pode ser marcada para o último dia do prazo. **Exceção: o aviso de dispensa
  eletrônica conta o próprio dia da publicação.** Só contam dias úteis (sem fins de semana,
  feriados e pontos facultativos). O formulário mostra a data mínima enquanto se preenche.
- **Remarcação após retificação do edital**: o prazo é contado de novo a partir da divulgação
  do edital retificado (art. 55, § 1º), salvo quando se marca que a alteração não compromete
  a formulação das propostas.

## Recursos

Com a sessão em andamento, o pregoeiro / agente registra o recurso informando as datas:
intimação ou lavratura da ata, notificação das empresas sobre o recurso (opcional, comum na
licitação presencial) e os prazos de razões, contrarrazões, reconsideração e decisão. O botão
“Sugerir prazos legais” preenche as datas em dias úteis (art. 165: 3 + 3 + 3 + até 10; as
contrarrazões contam da notificação das empresas, se houver), e todas podem ser ajustadas
enquanto o recurso corre (“Prazos do recurso”). Vencimentos em dia sem expediente são
recusados. A licitação fica “Em recurso”, o painel mostra o quadro **Em recurso — prazos**
com a etapa atual, e a situação só muda ao registrar a decisão.

## Parâmetros (Configurações)

Quem tem a permissão de parâmetros (Administrador e Gestor, por padrão) altera:

- **Nome da secretaria/órgão** exibido no cabeçalho e nas imagens.
- **Brasão do município**: imagem (PNG, JPG ou WebP) exibida no cabeçalho do sistema, na tela
  de login e no cabeçalho da imagem do WhatsApp, reduzida proporcionalmente para caber.
- **Modalidades**: nome, **sigla**, cor, ordem, se exige equipe, quem conduz (pregoeiro ou
  agente) e se funciona como credenciamento. O número do edital é digitado **sem a sigla**
  (ex.: `007/2026`) e aparece nas telas como `PE 007/2026`.
- **Exportação para o WhatsApp**: quais situações entram na imagem e no texto.
- **Situações da licitação**: nome, cor, ordem e fase. O comportamento segue a fase
  (planejamento, publicada, remarcada, suspensa, em andamento, concluída, encerrada). As
  situações do sistema podem ser renomeadas e recoloridas, mas não excluídas.

Tudo fica registrado na auditoria.

## Instalador para Windows (recomendado)

O instalador `AgendaLicitacoes-Instalador-X.Y.Z.exe` já traz tudo embutido — **não é preciso
instalar o Python**. Ele é gerado automaticamente pelo GitHub Actions a cada alteração:
em **Actions → Instalador do Windows → (execução mais recente) → Artifacts**; versões
marcadas com uma tag `vX.Y.Z` também ficam na página **Releases** do repositório.

No computador que vai hospedar o sistema (fica ligado no expediente), execute o instalador
como administrador. Ele:

- instala o programa em `C:\AgendaLicitacoes` e guarda os dados em
  `C:\ProgramData\AgendaLicitacoes`, acessível só a administradores;
- **compartilha a pasta do programa** como `\\NOME-DO-COMPUTADOR\Licitacoes`, somente leitura,
  com o atalho **“Abrir Agenda de Licitações”** para os demais usuários;
- **libera a porta 8080** no firewall (redes privadas e de domínio);
- faz o sistema **iniciar com o Windows**, mesmo sem ninguém logado;
- guarda **cópias do banco numa pasta do Google Drive** (veja abaixo);
- no primeiro acesso **pelo próprio computador servidor**, pede a criação da conta do
  administrador (veja “Primeiro acesso” abaixo).

Cada opção pode ser desmarcada no assistente. Para atualizar, basta executar o instalador da
nova versão (os dados são mantidos). A desinstalação (Painel de Controle → Programas)
remove o programa, o compartilhamento, a regra do firewall e o início automático, mas
**mantém os dados**. O registro do servidor fica em `C:\ProgramData\AgendaLicitacoes\servidor.log`.

### Cópia do banco no Google Drive

Não dá para colocar o banco em uso dentro da pasta do Google Drive: o Drive não trava
arquivos entre computadores e, sincronizando no meio de uma gravação, corromperia o banco
ou perderia alterações. Por isso o banco fica no computador anfitrião e o sistema envia
para a pasta do Drive **cópias completas e consistentes**:

```
...\Meu Drive\AgendaLicitacoes\
    licitacoes.sqlite3      ← última cópia (a cada 5 minutos, quando há alterações)
    brasao.png
    copias-diarias\         ← uma cópia por dia, dos últimos 30 dias
    anfitriao.json          ← trava: qual computador está servindo a agenda
    copia.json              ← quem fez a última cópia, e quando
```

- No Google Drive para computador, use **“Espelhar arquivos”** em “Meu Drive” e escolha uma
  pasta dentro de `C:\Users\...\Meu Drive`. A unidade virtual `G:` (modo “Transmitir
  arquivos”) só existe para o usuário logado e o sistema, que inicia com o Windows, não a
  enxerga.
- **Dois computadores nunca servem a agenda ao mesmo tempo:** o anfitrião renova a trava a
  cada minuto; outro computador que tente iniciar o sistema com a mesma pasta é recusado e
  recebe o endereço do anfitrião.
- **Se o anfitrião quebrar:** instale o programa em outro computador indicando a mesma pasta
  do Drive. Quando a trava fica 10 minutos sem renovação, ele restaura a última cópia (e o
  brasão) e assume. Se o antigo anfitrião voltar, ele percebe que perdeu a vez e para de
  enviar cópias.
- O administrador e o gestor veem a data da última cópia (ou a falha) em **Configurações**.
- Para restaurar um dia anterior: com o sistema parado, copie o arquivo de `copias-diarias`
  sobre `C:\ProgramData\AgendaLicitacoes\licitacoes.sqlite3`.

Sem o instalador: `python servidor.py --nuvem "C:\Users\fulano\Meu Drive\AgendaLicitacoes"`
(intervalo com `--copia-minutos`).

### Primeiro acesso

Enquanto o banco não tiver nenhum administrador, qualquer página leva à tela
**“Configuração inicial”**, onde se escolhem o nome, o login e a senha do administrador.
Ela só funciona **no próprio computador servidor** (atalho da área de trabalho,
`http://localhost:8080/`); pela rede aparece só o aviso para concluir a configuração no
servidor, para que ninguém se adiante e vire administrador. Depois que existe um
administrador a tela deixa de existir — inclusive em atualizações e em bancos restaurados
da cópia na nuvem. O sistema impede que um administrador tire o próprio acesso, então
sempre sobra ao menos um.

Como o instalador não tem assinatura digital, o Windows pode mostrar “O Windows protegeu o
computador”: clique em **Mais informações → Executar assim mesmo**.

## Instalação em pasta compartilhada (sem o instalador)

O programa fica numa pasta compartilhada e roda **num único computador**, o que hospeda a
pasta. Os demais usuários abrem o sistema **pela pasta compartilhada**, com dois cliques no
atalho “Abrir Agenda de Licitações”, sem instalar nada. Vários usuários podem usar ao mesmo
tempo.

```
\\SERVIDOR\Licitacoes\                    ← pasta compartilhada (somente leitura para os usuários)
    Abrir Agenda de Licitações.url          ← os usuários abrem este atalho
    Iniciar servidor.bat                    ← só no computador que hospeda a pasta
    licitacoes\, servidor.py, ...

C:\ProgramData\AgendaLicitacoes\           ← dados: NÃO compartilhar
    licitacoes.sqlite3, secret_key, brasao.png, venv\
```

**No computador que hospeda a pasta** (fica ligado durante o expediente):

1. Instale o [Python 3.10 ou mais novo](https://www.python.org/downloads/), marcando
   “Add python.exe to PATH”.
2. Copie o programa para a pasta (ex.: `C:\Licitacoes`) e compartilhe-a na rede com
   permissão **somente leitura** para os usuários.
3. Dê dois cliques em **`Iniciar servidor.bat`**. Na primeira vez ele prepara o ambiente.
   Deixe a janela aberta e, neste computador, abra `http://localhost:8080/` para criar a
   conta do administrador.
4. Se o Windows perguntar, permita o acesso do Python às **redes privadas**.
5. Para iniciar junto com o Windows: tecle `Win + R`, digite `shell:startup` e coloque ali
   um atalho para `Iniciar servidor.bat`.

**Nos demais computadores:** abra `\\SERVIDOR\Licitacoes` e dê dois cliques em
**“Abrir Agenda de Licitações”** (pode arrastá-lo para a área de trabalho). O atalho é
criado pelo servidor ao iniciar, com o nome do computador; se a rede não resolver nomes,
inicie com `Iniciar servidor.bat --endereco 192.168.0.10` (o IP do computador hospedeiro).

**Por que não abrir o programa direto da pasta em cada computador?** O banco de dados
(SQLite) não suporta gravações simultâneas de vários computadores sobre uma pasta de rede —
o arquivo pode corromper — e cada computador precisaria ter o Python. Com o sistema rodando
num só computador, todos usam o mesmo banco com segurança.

**Acesso simultâneo:** o servidor atende vários usuários em paralelo; quando duas pessoas
gravam ao mesmo tempo, uma espera a outra terminar. Se duas pessoas editarem a **mesma
licitação** ao mesmo tempo, a segunda é avisada de que a licitação foi alterada (e por quem)
e nada é sobrescrito: ela confere os dados atuais e refaz a alteração.

**Backup:** copie a pasta `C:\ProgramData\AgendaLicitacoes` (de preferência com o
servidor fechado).

## Instalação manual (linha de comando)

Ao atualizar uma instalação existente, rode de novo `pip install -r requirements.txt`
(a imagem do WhatsApp usa a biblioteca Pillow). O banco é atualizado sozinho na partida.

Requisito: Python 3.10 ou superior (Windows ou Linux). Não é preciso instalar banco de
dados: os dados ficam em um arquivo SQLite na pasta `instance/`.

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate     Linux: source .venv/bin/activate
pip install -r requirements.txt
python servidor.py --porta 8080
```

Na primeira execução, abra `http://localhost:8080/` no próprio servidor e crie a conta do
administrador. Os demais
servidores da secretaria acessam por `http://NOME-DO-SERVIDOR:8080/`.

Primeiros passos: cadastre os usuários (menu **Usuários**) e os servidores que compõem as
equipes (menu **Servidores**) antes de lançar as licitações.

Se precisar recuperar o acesso de administrador:

```bash
flask --app licitacoes criar-admin --login admin
```

### Configuração opcional (variáveis de ambiente)

| Variável         | Uso                                                                  |
|------------------|----------------------------------------------------------------------|
| `NOME_ORGAO`     | Nome exibido no topo das páginas (ex.: "Secretaria de Administração") |
| `SECRET_KEY`     | Chave das sessões; se omitida, é gerada em `instance/secret_key`     |
| `AGENDA_DADOS`   | Pasta de dados (o mesmo que `--dados`); padrão: `instance/`          |

### Recomendações

- **Backup**: copie periodicamente a pasta de dados (`instance/` ou a indicada em `--dados`),
  que contém o banco `licitacoes.sqlite3`.
- **Firewall**: libere a porta escolhida apenas para a rede interna.
- **Serviço**: para iniciar junto com o servidor, use o Agendador de Tarefas / NSSM no
  Windows, ou um serviço `systemd` no Linux.
- **HTTPS**: se a intranet tiver certificado, coloque o sistema atrás do IIS, Nginx ou
  Apache como proxy reverso.

## Desenvolvimento

```bash
pip install -r requirements.txt pytest
python -m pytest
```

Estrutura:

```
servidor.py              inicia o servidor (Waitress) e cria o atalho para os usuários
Iniciar servidor.bat     inicia o servidor no Windows (pasta compartilhada, sem instalador)
instalador/              empacotamento (PyInstaller), instalador (Inno Setup) e configuração
                         do Windows; gerados por .github/workflows/instalador.yml
licitacoes/
  __init__.py            criação da aplicação, CSRF, filtros, comandos
  perfis.py              perfis e valores padrão dos parâmetros
  auth.py                login, troca de senha e controle de acesso
  agenda.py              painel, calendário, cadastro, suspensão, WhatsApp e .ics
  admin.py               usuários, servidores, afastamentos e auditoria
  parametros.py          leitura dos parâmetros (modalidades, situações, permissões)
  config.py              telas de configuração (permissões e parâmetros)
  feriados.py            feriados, dias úteis e prazo mínimo legal
  equipe.py              regras da equipe (efetivos, férias e afastamentos)
  imagem.py              imagem para WhatsApp (fonte Inter em static/fontes, licença OFL)
  db.py                  esquema e acesso ao SQLite
  templates/, static/    telas
tests/                   testes automatizados
```
