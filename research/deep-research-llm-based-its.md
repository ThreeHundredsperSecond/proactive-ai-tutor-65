# Landscape scan современных LLM-based Intelligent Tutoring Systems

## Что сейчас называют LLM-based tutoring / LLM-based ITS

В литературе постепенно закрепляется различие между **LLM как образовательным собеседником** и **LLM как компонентом замкнутой тьюторской системы**. Обычный educational chatbot в основном реализует цикл `вопрос → генерация ответа`; ITS дополнительно наблюдает действия ученика, оценивает его состояние, выбирает педагогическое действие и обновляет модель ученика после взаимодействия. Классическая схема ITS — **domain model + student model + tutoring model + interface** — не исчезла: современные LLM-системы либо сохраняют эти модули, либо «схлопывают» часть из них внутрь одного LLM и дополняют retrieval, monitoring и другими внешними компонентами. citeturn16view0turn17view0

Поэтому наличие хорошего промпта вроде «веди себя как сократический тьютор» само по себе ещё не делает систему ITS. LearnLM, например, показывает отдельную важную линию — *pedagogical alignment / pedagogical instruction following*: модель обучают не просто давать правильную информацию, а вести себя согласно заданной педагогике. citeturn19view0 MathDial демонстрирует, зачем это нужно: сильная решающая LLM может быть плохим тьютором — сообщать решение слишком рано или давать неудачную обратную связь. citeturn20view0 Более «ITS-подобная» система появляется, когда к этому добавляются **оценка ответа, learner state, история, выбор следующего действия и контур адаптации**; именно learner modeling и pedagogical dialogue management свежий обзор LLM-ITS выделяет как отдельные ключевые способности. citeturn18view0turn18view1

Практически поле сейчас удобно представлять как континуум: **pedagogically prompted chatbot → grounded tutor → personalized tutor → stateful adaptive ITS → proactive/agentic ITS**. Это не официальная таксономия, а полезное архитектурное обобщение литературы ниже.

Русскоязычный поиск я тоже провёл; в нём значительно меньше работ, где явно описаны `student model → pedagogical policy → adaptive action` именно для LLM. Поэтому архитектурная часть карты опирается преимущественно на англоязычные peer-reviewed и primary sources, а не на слабые русскоязычные пересказы.

## Основные подходы и компоненты

Оценка распространённости ниже — **качественный synthesis**, а не измеренная доля публикаций. Хороший ориентир даёт свежий обзор LLM-based ITS, который группирует работы вокруг domain knowledge, learner-response evaluation, learner modeling и pedagogical dialogue management и отдельно различает modular и integrated architectures. citeturn16view0turn17view1

| Подход / компонент | Альтернативные термины | Что делает | Насколько типично | Показательный пример |
|---|---|---|---|---|
| **Grounding / RAG** | retrieval-augmented generation, knowledge-grounded tutoring, KB/KG augmentation, curriculum grounding | Ограничивает ответы учебными материалами/knowledge base, достаёт релевантные концепты, задачи и объяснения; уменьшает зависимость от parametric knowledge LLM. | **Очень распространено** | **TutorLLM** объединяет RAG с KT; в обзоре retrieval/grounding входит в современный Domain Model. citeturn19view1turn16view0 |
| **Learner / Student Model** | learner profile, student state, cognitive model, learner representation | Представляет текущие знания, ошибки, способности, иногда аффективное состояние, цели и предпочтения ученика. Это ключевое отличие полноценного ITS от stateless chatbot. | **Ядро** для ITS, хотя отсутствует у многих «LLM tutors» | Современный обзор прямо сохраняет Student Model как один из центральных блоков и выделяет KT, profiling, simulation и intent recognition. citeturn16view0turn18view0 |
| **Knowledge tracing / mastery tracking** | KT, skill mastery, concept mastery, cognitive diagnosis, knowledge-state estimation | По последовательности действий оценивает вероятность владения конкретными skills / knowledge components и прогнозирует будущий ответ. | **Часто**, особенно в genuinely adaptive ITS | **LLMKT** извлекает skills/correctness из диалога и отслеживает mastery; **TutorLLM** использует отдельный KT-модуль. citeturn19view2turn19view1 |
| **Assessment / evaluator** | learner-response evaluation, grading, correctness estimator, misconception diagnosis, critic / judge | Определяет правильность, качество решения, тип ошибки или misconception; результат становится сигналом для следующего шага и обновления student model. | **Очень распространено** | Обзор выделяет scoring, narrative evaluation и constructive feedback как отдельный класс задач; AIED-работа Scarlatos et al. использует student-outcome evaluator плюс pedagogical rubric. citeturn18view0turn20view2 |
| **Pedagogical policy / planner** | tutoring model, instructional policy, dialogue policy, teaching strategy, pedagogical controller | Решает **что делать дальше**: задать вопрос, дать hint, объяснить, увеличить/уменьшить сложность, проверить misconception, перейти к теме и т. п. | **Ядро как функция**; явный planner встречается реже | В классическом ITS Tutoring Model выбирает стратегию по student state. **MWPTutor** намеренно оставляет педагогическую policy в hand-crafted finite-state controller, используя LLM внутри неё. citeturn16view0turn19view3 |
| **Scaffolding / pedagogical dialogue management** | Socratic tutoring, hinting policy, guided questioning, tutor moves | Управляет формой помощи: не выдавать ответ сразу, а использовать progressive hints, questions, explanations, encouragement. | **Очень распространено** | Свежий survey выделяет Socratic questioning, scaffolded hinting и affect-aware feedback; MathDial размечает teacher moves и scaffolding. citeturn18view1turn20view0 |
| **Personalization / adaptation** | adaptive tutoring, personalized instruction, difficulty adaptation, learning-path adaptation | Использует learner state для изменения содержания, сложности, объяснений или последовательности заданий. Скорее сквозная функция, чем один модуль. | **Ядро** | TutorLLM выбирает рекомендации по predicted learning state; TASA калибрует вопросы и объяснения по mastery и forgetting. citeturn19view1turn21view0 |
| **Long-term memory** | persistent learner memory, episodic memory, learning history, longitudinal state | Хранит информацию между заданиями/сессиями: прошлые ошибки, mastery, события обучения, иногда preferences. Важно отличать от простого conversation context. | **Развивающийся подход** | **TASA** хранит structured persona + event memory + forgetting dynamics. LLM-KT также использует внешний sequence representation исторических взаимодействий. citeturn21view0turn18view1 |
| **Multi-agent architecture** | role-based agents, teacher–student–critic, orchestrated agents | Разделяет роли между несколькими LLM instances: tutor, simulated student, evaluator/dean, planner и т. п. Обычно нужен для decomposition, synthetic data или контроля policy. | **Развивающийся подход** | **SocraticLM** использует Dean–Teacher–Student pipeline: Teacher обучает, Student симулирует ученика, Dean корректирует педагогическое поведение Teacher. citeturn18view1turn18view2 |
| **Student simulator / outcome model** | simulated learner, student agent, user simulator, response predictor | Прогнозирует, как ученик отреагирует на конкретный teaching action. Позволяет сравнивать политики и обучать тьютора без постоянных экспериментов на реальных учениках. | **Развивающийся подход** | Scarlatos et al. оценивают candidate tutor actions LLM-based student model и оптимизируют tutor через DPO. citeturn20view2 |
| **Proactive tutoring** | proactive intervention, mixed-initiative tutoring, anticipatory support, tutor-initiated interaction | Система сама инициирует помощь или предлагает следующий релевантный шаг, а не ждёт вопроса ученика. | **Развивающийся подход** | **SCALA** заранее предсказывает вероятные вопросы студентов и показывает их перед/вокруг лекции; система развёрнута на курсе с >1,500 студентов. citeturn20view1 |
| **Pedagogical alignment / guardrails** | instructional alignment, pedagogical instruction following, teaching constraints | Не даёт генератору скатиться в answer-giving; задаёт допустимые tutor moves, pedagogy, tone и правила disclosure. | **Часто / очень распространено** | **LearnLM** обучается pedagogical instruction following; **MWPTutor** жёстко ограничивает генерацию pedagogical state machine. citeturn19view0turn19view3 |

Здесь полезно провести ещё одно различие: **learner model** шире, чем **knowledge tracing**. KT отвечает примерно на вопрос «что ученик знает и с какой вероятностью?», тогда как learner model может также хранить misconceptions, историю, engagement, preferences, цели и другие признаки. Современный survey именно так разделяет knowledge state, cognitive profile и interaction history. citeturn18view0

И аналогично, **long-term memory ≠ student model**. Memory — механизм хранения; student model — интерпретированное состояние ученика. Хорошая архитектура может, например, хранить сотни событий в episodic store, но подавать planner'у компактный вектор `mastery(skill_i), misconceptions, recent struggles, goals`.

## Типичные архитектурные паттерны

### Grounded pedagogical chatbot

```text
Student
  → Query + dialogue context
  → Retriever → course materials
  → LLM + pedagogical prompt
  → Hint / explanation / question
  → Student
```

Это сегодня самый простой практический upgrade от обычного chatbot: LLM получает проверенный curricular context и инструкции «не выдавай решение, используй hints». RAG повышает grounding, но **сам по себе не создаёт адаптацию во времени**: два ученика с одинаковым запросом всё ещё могут получить почти одинаковый ответ. TutorLLM и современная трактовка Domain Model показывают переход от простого RAG к связке retrieval + learner state. citeturn19view1turn16view0

### Closed-loop adaptive tutor

```text
Student
  → Response
  → Assessor
  → Student Model / KT
  → Pedagogical Policy
  → RAG / Domain Model
  → LLM
  → Next task / hint / feedback
  → Student
```

Это наиболее прямое продолжение классического ITS. Критически важен переход **`estimate state → choose pedagogical action`**, а LLM можно использовать лишь для реализации выбранного действия — например, сформулировать hint естественным языком. Такая декомпозиция делает систему значительно более контролируемой и объяснимой. citeturn16view0turn18view0

### Hybrid controller + LLM

```text
Student
  → State / error classification
  → Explicit pedagogical controller
  → selected tutor move
  → LLM
  → constrained utterance
  → Student
```

В **MWPTutor** педагогическая структура задаётся finite-state transducer, а LLM добавляет языковую гибкость. Авторы получили более высокую human-evaluated tutoring quality, чем у свободно инструктированного GPT-4, что хорошо иллюстрирует идею: **LLM не обязан быть policy engine**. citeturn19view3

### Stateful tutor with longitudinal memory

```text
Student
  → Current interaction
  → Assessment
  → Persistent history / event memory
  → Mastery + forgetting update
  → Planner / adaptation
  → RAG
  → LLM
  → personalized next interaction
  → Student
```

Здесь student state живёт дольше одной chat session. **TASA** — показательный свежий пример: structured proficiency persona, event memory, KT и модель забывания вместе определяют сложность следующих вопросов и объяснений. citeturn21view0 Это ближе всего к архитектуре, которую обычно имеют в виду, говоря о *longitudinal personalized tutor*.

### Agentic / outcome-optimized tutor

```text
Student state
  → Planner / candidate tutor actions
  → Tutor LLM(s)
  → Student simulator + pedagogical evaluator
  → select / learn policy
  → Tutor LLM
  → Student
```

Здесь «разумность» вынесена на уровень выбора между педагогическими действиями. В AIED 2025 несколько candidate tutor utterances оцениваются по predicted next-student correctness и pedagogical rubric, после чего эта preference signal используется для обучения tutor policy. citeturn20view2 Multi-agent варианты добавляют Teacher / Student / Critic-or-Dean роли; это интересно исследовательски, но пока нельзя считать обязательной архитектурой ITS. citeturn18view2

## Мета поля

**Базовое ядро полноценного adaptive LLM tutor** я бы описал не через конкретные технологии, а через пять функций:

```text
Domain grounding
     ↓
Observe learner → Estimate learner state
                        ↓
                 Choose teaching action
                        ↓
                   Generate/execute
                        ↓
                 Observe result again
```

Это практически современная версия классического closed loop `Domain Model ↔ Student Model ↔ Tutoring Model ↔ Interface`. LLM может реализовывать один, несколько или почти все блоки; свежий survey прямо делит LLM-ITS на **modular** и **integrated** архитектуры. citeturn16view0turn17view0

**Что чаще всего естественно используется вместе.** `RAG + pedagogical prompt/guardrails` — базовая связка для grounded tutor. `Assessment + learner model/KT + adaptation` образует собственно adaptive loop. `KT + RAG` позволяет выбирать не просто правильный материал, а материал, релевантный текущему mastery, как в TutorLLM. citeturn19view1 Для более зрелой stateful архитектуры появляется связка `persistent history → student model → planner → intervention`, а не непосредственная подстановка всей chat history в prompt.

**Самая активная зона развития сейчас — не generation, а control loop.** Learner modeling по открытым диалогам уже становится самостоятельной задачей: LLMKT размечает skills/correctness и отслеживает mastery на протяжении диалога, а survey 2026 перечисляет несколько LLM-based KT/cognitive-diagnosis подходов. citeturn19view2turn18view0 Параллельно появляется optimization педагогической policy по predicted learning outcomes, а не только по «качеству ответа». citeturn20view2

Ещё одна быстро развивающаяся область — **evaluation**. Оценить тьютора через factual QA benchmark недостаточно: TutorGym помещает LLM внутрь реальных ITS environments и проверяет hints, step-level feedback и следующие действия. В их начальном эксперименте современные LLM были далеко не идеальными тьюторами: например, ни одна не превзошла chance level при распознавании неправильных действий, а правильность next-step actions составляла примерно 52–70%. citeturn21view1 Это важный сигнал против предположения «сильнее reasoning benchmark → автоматически лучше tutor».

**Развивающиеся, но ещё не стандартные компоненты** — persistent episodic memory, explicit forgetting models, student simulators, policy optimization и proactive interventions. TASA уже соединяет memory + forgetting + KT, а SCALA переводит взаимодействие от полностью reactive к tutor-initiated support. citeturn21view0turn20view1

**Скорее экспериментальным слоем** пока выглядят сложные multi-agent topologies. Они действительно встречаются — например, Dean–Teacher–Student в SocraticLM, — но архитектурная ценность обычно исходит из **разделения ролей**, а не из самого факта наличия нескольких LLM. citeturn18view2 Для production-системы `planner + evaluator + generator` вполне может быть тремя вызовами одной модели или тремя обычными сервисами, а не «агентами».

Наконец, поле пока не решило фундаментальную проблему **objective function**. Хорошая фраза тьютора, правильный следующий ответ ученика и долгосрочное обучение — не одно и то же. Работа Scarlatos et al. уже оптимизирует predicted correctness следующего ответа, но сами авторы подчёркивают ограничение: обучение проводилось с simulated student, не с реальными учениками. citeturn20view2 Свежий survey поэтому называет будущей задачей оценку не только response quality, но и appropriateness педагогической стратегии и образовательного эффекта. citeturn17view1

## Показательные работы и системы

| Работа | Год | Зачем посмотреть |
|---|---:|---|
| **[LLM-based Intelligent Tutoring Systems: A Survey](https://personal.utdallas.edu/~vince/papers/ijcai26.pdf)** | 2026 | Самая удобная из найденных свежих **архитектурных карт поля**: classical Domain/Student/Tutoring models → modular vs integrated LLM-ITS; таблицы learner modeling, assessment и pedagogical dialogue methods. citeturn16view0turn17view1 |
| **[MathDial: A Dialogue Tutoring Dataset with Rich Pedagogical Properties Grounded in Math Reasoning Problems](https://arxiv.org/abs/2305.14536)** | 2023 | Хорошая отправная точка для понимания разницы **solver vs tutor**; teacher-move taxonomy, scaffolding и interactive evaluation. citeturn20view0 |
| **[AutoTutor meets Large Language Models: A Language Model Tutor with Rich Pedagogy and Guardrails](https://arxiv.org/abs/2402.09216)** | 2024 | Очень чистый пример **hybrid ITS**: explicit pedagogical state machine остаётся снаружи, LLM отвечает за гибкую генерацию. citeturn19view3 |
| **[LearnLM: Improving Gemini for Learning](https://arxiv.org/abs/2412.16429)** | 2024/2025 | Ключевой пример линии **pedagogical alignment**: не архитектура полного stateful ITS, а обучение foundation model правильному tutoring behaviour. Полезно как нижний LLM-layer будущей системы. citeturn19view0 |
| **[Exploring Knowledge Tracing in Tutor-Student Dialogues using LLMs / LLMKT](https://arxiv.org/abs/2409.16490)** | 2024 / LAK 2025 | Один из самых релевантных papers для **student state из свободного tutoring dialogue**: skill extraction, correctness estimation и KT на протяжении разговора. citeturn19view2 |
| **[TutorLLM: Customizing Learning Recommendations with Knowledge Tracing and Retrieval-Augmented Generation](https://arxiv.org/abs/2502.15709)** | 2025 | Простая и полезная reference architecture **KT + RAG + LLM**: learner state влияет на retrieval/recommendation, а не просто добавляется в system prompt. citeturn19view1 |
| **[Training LLM-based Tutors to Improve Student Learning Outcomes in Dialogues](https://arxiv.org/abs/2503.06424)** | 2025 | Очень важное направление: **student model → predicted outcome → pedagogical evaluator → learned tutor policy**. То есть оптимизируется выбор tutor action, а не только текст. citeturn20view2 |
| **[TutorGym: A Testbed for Evaluating AI Agents as Tutors and Students](https://arxiv.org/abs/2505.01563)** | 2025 | Полезный benchmark/testbed, потому что проверяет LLM **как интерактивного тьютора внутри существующего ITS**, а не как решатель задач; содержит 223 tutor domains. citeturn21view1 |
| **[Teaching According to Students' Aptitude: Personalized Mathematics Tutoring via Persona-, Memory-, and Forgetting-Aware LLMs](https://arxiv.org/abs/2511.15163)** | 2025 | Наиболее прямой из найденных примеров архитектуры **persistent learner state + event memory + forgetting + KT + difficulty adaptation**. Пока скорее research prototype, но концептуально очень релевантен. citeturn21view0 |
| **[Let LLM Tutors Ask First: Proactive LLM-Based Tutoring at Scale in a 1,500-Student Online Classroom](https://aclanthology.org/2026.acl-industry.107/)** | 2026 | Редкий убедительный пример **proactive tutoring в реальном deployment**: SCALA генерирует вероятные student questions заранее и была развернута семестр на курсе Python с >1,500 студентов. citeturn20view1 |

Из этого набора для быстрого входа я бы в первую очередь читал **Survey → MWPTutor → LLMKT → Scarlatos AIED → TASA/SCALA**. Вместе они почти полностью покрывают переход от классического ITS к `state → policy → action → update`, persistent memory и proactive behaviour. citeturn16view0turn19view3turn19view2turn20view2turn21view0turn20view1

## Куда копать дальше

**Learner model как отдельный persistent service.** Для проектирования адаптивного тьютора это, вероятно, наиболее важный слой. Стоит исследовать гибрид `structured mastery per concept + misconception hypotheses + episodic interaction memory`, причём хранить raw history отдельно от компактного педагогического state. LLMKT показывает, что skill-level state можно извлекать даже из свободного диалога; TASA добавляет temporal memory и forgetting. citeturn19view2turn21view0

**Explicit pedagogical policy поверх генератора.** Практически интересна архитектура, где planner выбирает из ограниченного action space вроде:

```text
ASK_DIAGNOSTIC
GIVE_SMALL_HINT
GIVE_STRONG_HINT
EXPLAIN_CONCEPT
ASK_REFLECTION
PRACTICE_SKILL_X
REVIEW_SKILL_Y
ADVANCE_DIFFICULTY
DECREASE_DIFFICULTY
PAUSE / MOTIVATE
```

а LLM только реализует выбранный action. MWPTutor показывает ценность explicit controller, а работа AIED 2025 — следующий шаг, где policy можно обучать по predicted learner outcomes. citeturn19view3turn20view2

**Развести content retrieval и pedagogical retrieval.** Обычный RAG отвечает «какой материал релевантен вопросу?», но adaptive tutor нуждается ещё в запросе «какой материал/задача релевантны *этому ученику сейчас*?». Связка `student state → retrieval filters/ranking → pedagogical planner → LLM`, которую намечает TutorLLM, архитектурно перспективнее простого semantic RAG по курсу. citeturn19view1

**Proactive intervention policy.** SCALA показывает feasibility tutor-initiated interaction, но следующий более сильный вариант — не просто заранее предсказывать FAQ, а решать **когда вмешиваться и зачем** по learner state: например, `mastery drop`, repeated misconception, overdue review из forgetting model, длительное бездействие или mismatch сложности. SCALA подтверждает саму ценность proactive paradigm, тогда как persistent state/forgetting из TASA даёт естественные trigger signals для её развития. citeturn20view1turn21view0

**Long-horizon evaluation вместо оценки отдельных ответов.** Для такой системы конечная метрика должна отделять `response quality`, `next-turn success`, `mastery gain`, `retention` и нежелательную зависимость от тьютора. TutorGym уже двигает evaluation от QA к интерактивному step-level поведению, а outcome-optimized tutoring показывает, как learner model может стать частью training/evaluation loop. citeturn21view1turn20view2

В итоге наиболее перспективная reference architecture для **адаптивного LLM-тьютора с долговременным состоянием и проактивностью** выглядит не как «ChatGPT + память», а примерно так:

```text
                         ┌── Curriculum / KB / RAG ──┐
                         │                           ↓
Student → Observation → Assessment → Learner State → Pedagogical Planner
      ↑                      │            ↑                 │
      │                      │      persistent memory       │
      │                      │      + mastery/KT            │
      │                      │      + forgetting            │
      │                      │                              ↓
      └──── Tutor output ← LLM realizer ← selected pedagogical action
                                ↑
                         guardrails / evaluator

          Scheduler / trigger engine ──→ proactive intervention
```

То есть **LLM лучше рассматривать как мощный reasoning/generation layer внутри ITS, а не как сам ITS**. Главная исследовательская граница поля сейчас смещается от «как заставить LLM хорошо объяснять» к более классической и более трудной задаче: **что система знает об этом ученике, какое педагогическое действие выбрать сейчас, когда самой инициировать его и как понять через недели, что оно действительно помогло**. Это направление хорошо согласуется одновременно со свежей архитектурной таксономией LLM-ITS, работами по KT и long-term state, outcome-driven policy learning и первым крупным proactive deployment. citeturn16view0turn19view2turn20view2turn21view0turn20view1