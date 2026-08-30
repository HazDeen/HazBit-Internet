import { ArrowLeft, FileCheck2, Headphones, Mail, MessageCircle, ShieldCheck, type LucideIcon } from "lucide-react";
import { PublicHeader } from "../../components/layout/PublicHeader";
import { legalConfig } from "../../config/legal";
import { useI18n } from "../../i18n";
import type { Theme } from "../../types";
import "./legal.css";

export type LegalRoute = "privacy" | "terms" | "contacts";

interface Props { route: LegalRoute; theme: Theme; onThemeChange: (theme: Theme) => void; authenticated: boolean; onAccountAction: () => void }

export function PublicLegalPage({ route, theme, onThemeChange, authenticated, onAccountAction }: Props) {
  const { t } = useI18n();
  const content = route === "privacy" ? <Privacy /> : route === "terms" ? <Terms /> : <Contacts />;
  return <main className="legal-page"><div className="public-page__mesh" /><PublicHeader theme={theme} onThemeChange={onThemeChange} authenticated={authenticated} onAccountAction={onAccountAction} /><div className="legal-wrap"><a className="legal-back" href="#top"><ArrowLeft />{t("Back to website", "Вернуться на сайт")}</a>{content}</div><LegalFooter /></main>;
}

function Privacy() {
  const { t } = useI18n();
  return <article className="legal-document">
    <LegalHead icon={ShieldCheck} eyebrow={t("LEGAL · PRIVACY", "ДОКУМЕНТЫ · КОНФИДЕНЦИАЛЬНОСТЬ")} title={t("Privacy Policy", "Политика конфиденциальности")} />
    <LegalLead>{t(
      `Effective date: ${legalConfig.effectiveDate}. This Privacy Policy governs the collection, use and protection of information from users of ${legalConfig.projectName}. Account identifiers, technical information and interaction history are collected. Data is used to operate the Service, communicate with the User and analyse its operation. Information may be transferred to third parties only in cases established by law or with the User’s consent. Data is stored for the necessary period and protected within reasonable measures. The User independently bears the risks related to transmitting information. The Administration may amend this Policy without notice; continued use means acceptance of the amended Policy.`,
      `Дата вступления в силу: ${legalConfig.effectiveDate}. Политика конфиденциальности регулирует сбор, использование и защиту информации пользователей сервиса ${legalConfig.projectName}. Собираются идентификаторы аккаунта, техническая информация и история взаимодействий. Данные используются для обеспечения работы сервиса, связи с пользователем и анализа. Передача информации третьим лицам возможна только в законодательно установленных случаях или с согласия пользователя. Хранение данных осуществляется в течение необходимого срока, их защита — в разумных пределах. Пользователь самостоятельно несёт ответственность за риски, связанные с передачей данных. Администрация вправе вносить изменения в Политику без уведомления — согласие считается принятым при дальнейшем использовании сервиса.`,
    )}</LegalLead>
    <LegalSections items={[
      {
        title: t("1. General provisions", "1. Общие положения"),
        paragraphs: [
          t(`1.1. This Privacy Policy (the “Policy”) governs the processing and protection of information that the User provides while using ${legalConfig.projectName} (the “Service”).`, `1.1. Настоящая Политика конфиденциальности (далее — «Политика») регулирует порядок обработки и защиты информации, которую Пользователь передаёт при использовании сервиса ${legalConfig.projectName} (далее — «Сервис»).`),
          t("1.2. By using the Service, the User confirms consent to this Policy. If the User does not agree, the User must stop using the Service.", "1.2. Используя Сервис, Пользователь подтверждает своё согласие с условиями Политики. Если Пользователь не согласен с условиями — он обязан прекратить использование Сервиса."),
        ],
      },
      {
        title: t("2. Information collection", "2. Сбор информации"),
        paragraphs: [t("2.1. The Service may collect the following types of data:", "2.1. Сервис может собирать следующие типы данных:")],
        bullets: [
          t("account identifiers (login, ID, nickname and similar data);", "идентификаторы аккаунта (логин, ID, никнейм и т.п.);"),
          t("technical information (IP address, browser, device and operating system data);", "техническую информацию (IP-адрес, данные о браузере, устройстве и операционной системе);"),
          t("history of interactions with the Service.", "историю взаимодействий с Сервисом."),
        ],
        after: [t("2.2. The Service does not require passport data, documents, photos or other personal information, except for the minimum necessary to operate the Service.", "2.2. Сервис не требует от Пользователя предоставления паспортных данных, документов, фотографий или другой личной информации, кроме минимально необходимой для работы.")],
      },
      {
        title: t("3. Use of information", "3. Использование информации"),
        paragraphs: [t("3.1. The Service may use received information solely to:", "3.1. Сервис может использовать полученную информацию исключительно для:")],
        bullets: [
          t("ensure the Service functionality;", "обеспечения работы функционала;"),
          t("communicate with the User, including notifications and support;", "связи с Пользователем (в том числе для уведомлений и поддержки);"),
          t("analyse and improve the Service.", "анализа и улучшения работы Сервиса."),
        ],
      },
      {
        title: t("4. Transfer of information to third parties", "4. Передача информации третьим лицам"),
        paragraphs: [t("4.1. The Administration does not transfer received data to third parties, except when:", "4.1. Администрация не передаёт полученные данные третьим лицам, за исключением случаев:")],
        bullets: [
          t("required by law;", "если это требуется по закону;"),
          t("necessary to fulfil obligations to the User, for example when working with payment systems;", "если это необходимо для исполнения обязательств перед Пользователем (например, при работе с платёжными системами);"),
          t("the User has given consent.", "если Пользователь сам дал на это согласие."),
        ],
      },
      {
        title: t("5. Data storage and protection", "5. Хранение и защита данных"),
        paragraphs: [
          t("5.1. Data is stored for the period necessary to achieve the purposes of processing.", "5.1. Данные хранятся в течение срока, необходимого для достижения целей обработки."),
          t("5.2. The Administration takes reasonable measures to protect data, but does not guarantee absolute security when information is transmitted over the internet.", "5.2. Администрация принимает разумные меры для защиты данных, но не гарантирует абсолютную безопасность информации при передаче через интернет."),
        ],
      },
      {
        title: t("6. Disclaimer", "6. Отказ от ответственности"),
        paragraphs: [
          t("6.1. The User understands and agrees that sending information over the internet always involves risks.", "6.1. Пользователь понимает и соглашается, что передача информации через интернет всегда сопряжена с рисками."),
          t("6.2. The Administration is not liable for loss, theft or disclosure of data caused by third parties or the User.", "6.2. Администрация не несёт ответственности за утрату, кражу или раскрытие данных, если это произошло по вине третьих лиц или самого Пользователя."),
        ],
      },
      {
        title: t("7. Changes to the Policy", "7. Изменения в Политике"),
        paragraphs: [
          t("7.1. The Administration may change this Policy without prior notice.", "7.1. Администрация вправе изменять условия Политики без предварительного уведомления."),
          t("7.2. Continued use of the Service after changes means acceptance of the new version.", "7.2. Продолжение использования Сервиса после внесения изменений означает согласие Пользователя с новой редакцией Политики."),
        ],
      },
    ]} />
  </article>;
}

function Terms() {
  const { t } = useI18n();
  return <article className="legal-document">
    <LegalHead icon={FileCheck2} eyebrow={t("LEGAL · SERVICE", "ДОКУМЕНТЫ · СЕРВИС")} title={t("User Agreement", "Пользовательское соглашение")} />
    <LegalLead>{t(`Effective date: ${legalConfig.effectiveDate}. This User Agreement applies to use of ${legalConfig.projectName}.`, `Дата вступления в силу: ${legalConfig.effectiveDate}. Настоящее Пользовательское соглашение регулирует порядок использования сервиса ${legalConfig.projectName}.`)}</LegalLead>
    <LegalSections items={[
      {
        title: t("1. General provisions", "1. Общие положения"),
        paragraphs: [
          t(`1.1. This User Agreement (the “Agreement”) regulates the use of the ${legalConfig.projectName} online service (the “Service”) provided by the Administration.`, `1.1. Настоящее Пользовательское соглашение (далее — «Соглашение») регулирует порядок использования онлайн-сервиса ${legalConfig.projectName} (далее — «Сервис»), предоставляемого Администрацией.`),
          t("1.2. By using the Service, including opening a bot, registering, paying for services or gaining access to materials, the User confirms they have read and accept this Agreement in full.", "1.2. Используя Сервис, включая запуск бота, регистрацию, оплату услуг или получение доступа к материалам, Пользователь подтверждает, что полностью ознакомился с условиями настоящего Соглашения и принимает их в полном объёме."),
          t("1.3. If the User does not agree with this Agreement, the User must stop using the Service.", "1.3. В случае несогласия с условиями Соглашения Пользователь обязан прекратить использование Сервиса."),
        ],
      },
      {
        title: t("2. Nature of services and digital goods", "2. Характер услуг и цифровых товаров"),
        paragraphs: [
          t("2.1. The Service provides intangible digital goods and services, including but not limited to information materials, training programs, consultations, digital products and service support.", "2.1. Сервис предоставляет цифровые товары и услуги нематериального характера, включая, но не ограничиваясь: информационные материалы, обучающие программы, консультации, цифровые продукты и сервисные услуги."),
          t("2.2. Materials provided through the Service may include:", "2.2. Материалы, предоставляемые через Сервис, могут включать:"),
        ],
        bullets: [
          t("information from public sources;", "информацию из открытых источников;"),
          t("copyright materials of the Administration and/or third parties;", "авторские материалы Администрации и/или третьих лиц;"),
          t("analytical reviews, selections, recommendations and structured data.", "аналитические обзоры, подборки, рекомендации, структурированные данные."),
        ],
        after: [
          t("2.3. The User understands and agrees that the value of the Service’s digital goods and services lies in systematisation, analysis, presentation, support and updates, rather than in the exclusivity of individual information fragments.", "2.3. Пользователь осознаёт и соглашается, что ценность цифровых товаров и услуг Сервиса заключается в систематизации, анализе, форме подачи, сопровождении, поддержке и обновлениях, а не в эксклюзивности отдельных фрагментов информации."),
          t("2.4. The Service does not claim or guarantee the uniqueness, exclusivity or unavailability of individual material elements outside the Service.", "2.4. Сервис не заявляет и не гарантирует уникальность, исключительность или недоступность отдельных элементов материалов вне Сервиса."),
        ],
      },
      {
        title: t("3. Disclaimer and liability", "3. Отказ от гарантий и ответственности"),
        paragraphs: [
          t("3.1. The Service is provided on an “AS IS” basis.", "3.1. Сервис предоставляется на условиях «AS IS» («как есть»)."),
          t("3.2. The Administration does not guarantee:", "3.2. Администрация не гарантирует:"),
        ],
        bullets: [
          t("that the Service will meet the User’s expectations;", "соответствие Сервиса ожиданиям Пользователя;"),
          t("any financial, commercial, professional or other results;", "достижение каких-либо финансовых, коммерческих, профессиональных или иных результатов;"),
          t("uninterrupted and error-free operation of the Service.", "бесперебойную и безошибочную работу Сервиса."),
        ],
        after: [
          t("3.3. The Administration is not liable for:", "3.3. Администрация не несёт ответственности за:"),
        ],
        secondaryBullets: [
          t("any direct or indirect losses, including lost profit;", "любые прямые или косвенные убытки, включая упущенную выгоду;"),
          t("consequences of the User applying received materials;", "последствия применения Пользователем полученных материалов;"),
          t("acts or omissions of third parties;", "действия или бездействие третьих лиц;"),
          t("temporary technical failures and access restrictions.", "временные технические сбои и ограничения доступа."),
        ],
        final: [t("3.4. All decisions on the use of materials, recommendations and services are made by the User independently and at their own risk.", "3.4. Все решения о применении материалов, рекомендаций и услуг принимаются Пользователем самостоятельно и на его риск.")],
      },
      {
        title: t("4. Lawful use", "4. Законность использования"),
        paragraphs: [
          t("4.1. The Service is not intended to encourage, organise or facilitate unlawful activities.", "4.1. Сервис не предназначен для поощрения, организации или содействия противоправной деятельности."),
          t("4.2. The User agrees to use the Service only within applicable law and third-party rules.", "4.2. Пользователь обязуется использовать Сервис исключительно в рамках применимого законодательства и правил третьих сторон."),
          t("4.3. The User bears full responsibility for the lawful use of the Service’s materials and services.", "4.3. Ответственность за законность использования материалов и услуг Сервиса полностью возлагается на Пользователя."),
        ],
      },
      {
        title: t("5. Intellectual property", "5. Интеллектуальная собственность"),
        paragraphs: [
          t("5.1. All materials published in the Service are protected by intellectual property law.", "5.1. Все материалы, размещённые в Сервисе, охраняются законодательством об интеллектуальной собственности."),
          t("5.2. The User may not copy, distribute, resell, transfer to third parties or otherwise use Service materials without the copyright holder’s permission.", "5.2. Пользователю запрещается копировать, распространять, перепродавать, передавать третьим лицам или иным образом использовать материалы Сервиса без разрешения правообладателя."),
          t("5.3. Infringement of intellectual property rights may result in access restriction without compensation.", "5.3. Нарушение прав интеллектуальной собственности может повлечь ограничение доступа к Сервису без компенсации."),
        ],
      },
      {
        title: t("6. Access restriction", "6. Ограничение доступа"),
        paragraphs: [t("6.1. The Administration may suspend or restrict the User’s access to the Service in case of:", "6.1. Администрация вправе приостановить или ограничить доступ Пользователя к Сервису в случае:")],
        bullets: [
          t("violation of this Agreement;", "нарушения условий настоящего Соглашения;"),
          t("detected abuse;", "выявления злоупотреблений;"),
          t("legal or payment-provider requirements.", "требований законодательства или платёжных провайдеров."),
        ],
        after: [
          t("6.2. Restricting access does not release the User from obligations that arose earlier.", "6.2. Ограничение доступа не освобождает Пользователя от обязательств, возникших ранее."),
          t("6.3. The Administration reserves the right to refuse service to Users whose actions may create increased risks for the Service, payment providers or third parties.", "6.3. Администрация оставляет за собой право отказывать в обслуживании Пользователям, чьи действия могут создавать повышенные риски для Сервиса, платёжных провайдеров или третьих лиц."),
        ],
      },
      {
        title: t("7. Payments and refunds", "7. Платежи и возвраты"),
        paragraphs: [
          t("7.1. Payment for services and digital goods is made on the terms displayed in the Service before payment.", "7.1. Оплата услуг и цифровых товаров производится на условиях, указанных в Сервисе до момента оплаты."),
          t("7.2. Due to the intangible nature of digital goods and services, refunds are not made after access is granted, except as stated below.", "7.2. В связи с нематериальным характером цифровых товаров и услуг, возврат денежных средств после предоставления доступа не осуществляется, за исключением случаев, указанных ниже."),
          t("7.3. A refund is possible only if:", "7.3. Возврат средств возможен только если:"),
        ],
        bullets: [
          t("the service was not provided due to a technical fault of the Service;", "услуга не была оказана по технической вине Сервиса;"),
          t("access to the digital good was not actually provided.", "доступ к цифровому товару фактически не был предоставлен."),
        ],
        after: [
          t(`7.4. To request a refund, the User must contact support at ${legalConfig.supportEmail} within 24 hours after payment.`, `7.4. Для рассмотрения вопроса о возврате Пользователь обязан обратиться в службу поддержки по адресу ${legalConfig.supportEmail} в течение 24 часов с момента оплаты.`),
          t("7.5. A refund decision is made by the Administration individually.", "7.5. Решение о возврате принимается Администрацией индивидуально."),
          t("7.6. The User confirms that they will not initiate a chargeback through payment systems without first contacting the Service support team.", "7.6. Пользователь подтверждает, что обязуется не инициировать возврат платежа (chargeback) через платёжные системы без предварительного обращения в службу поддержки Сервиса."),
        ],
      },
      {
        title: t("8. Confidentiality", "8. Конфиденциальность"),
        paragraphs: [
          t("8.1. The Administration may collect the minimum technical data necessary for the Service to operate.", "8.1. Администрация может собирать минимально необходимые технические данные для обеспечения работы Сервиса."),
          t("8.2. The Administration takes reasonable measures to protect data, but does not guarantee the absolute security of transmitted information.", "8.2. Администрация принимает разумные меры для защиты данных, однако не гарантирует абсолютную безопасность передаваемой информации."),
        ],
      },
      {
        title: t("9. Changes to the terms", "9. Изменение условий"),
        paragraphs: [
          t("9.1. The Administration may amend this Agreement.", "9.1. Администрация вправе вносить изменения в настоящее Соглашение."),
          t("9.2. The current version of the Agreement is published in the Service.", "9.2. Актуальная версия Соглашения публикуется в Сервисе."),
          t("9.3. Continued use of the Service means acceptance of the updated terms.", "9.3. Продолжение использования Сервиса означает согласие Пользователя с обновлёнными условиями."),
        ],
      },
      {
        title: t("10. Contact information", "10. Контактная информация"),
        paragraphs: [
          t(`10.1. For all questions, the User may contact the support service through a ticket in the account or by email at ${legalConfig.supportEmail}.`, `10.1. По всем вопросам Пользователь может обратиться в службу поддержки через тикет в личном кабинете или по адресу ${legalConfig.supportEmail}.`),
          t("By using the Service, including opening the bot and/or entering the /start command, the User confirms that they have read and accept this Agreement in full.", "Используя Сервис (в том числе запуская бота и/или вводя команду /start), Пользователь подтверждает, что ознакомлен с настоящим Соглашением и принимает его условия в полном объёме."),
        ],
      },
    ]} />
  </article>;
}

function Contacts() {
  const { t } = useI18n();
  return <article className="legal-document contacts-document"><LegalHead icon={Headphones} eyebrow={t("SUPPORT", "ПОДДЕРЖКА")} title={t("We are here to help", "Мы на связи")} /><p>{t("Use a private support ticket for account, connection, payment and refund questions. You may also contact us directly.", "Создайте приватный тикет по вопросам аккаунта, подключения, оплаты или возврата. Также можно связаться напрямую.")}</p><div className="contact-grid"><a href={`mailto:${legalConfig.supportEmail}`}><Mail /><span><small>Email</small><b>{legalConfig.supportEmail}</b></span></a><a href={`https://t.me/${legalConfig.supportTelegram.replace(/^@/, "")}`} target="_blank" rel="noreferrer"><MessageCircle /><span><small>Telegram</small><b>{legalConfig.supportTelegram}</b></span></a><a href="#support"><Headphones /><span><small>{t("Account", "Личный кабинет")}</small><b>{t("Open a support ticket", "Создать тикет")}</b></span></a></div><section className="operator-card"><small>{t("SERVICE OPERATOR", "ОПЕРАТОР СЕРВИСА")}</small><h2>{legalConfig.operatorName}</h2><p>{legalConfig.projectName} · {t("online customer support", "онлайн-поддержка пользователей")}</p></section></article>;
}

function LegalHead({ icon: Icon, eyebrow, title }: { icon: LucideIcon; eyebrow: string; title: string }) { return <header className="legal-head"><span><Icon /></span><div><small>{eyebrow}</small><h1>{title}</h1></div></header>; }
function LegalLead({ children }: { children: string }) { return <p className="legal-lead">{children}</p>; }

interface LegalSection {
  title: string;
  paragraphs: string[];
  bullets?: string[];
  after?: string[];
  secondaryBullets?: string[];
  final?: string[];
}

function LegalSections({ items }: { items: LegalSection[] }) {
  return <div className="legal-sections">{items.map((item) => <section key={item.title}>
    <h2>{item.title}</h2>
    {item.paragraphs.map((copy) => <p key={copy}>{copy}</p>)}
    {item.bullets && <ul>{item.bullets.map((copy) => <li key={copy}>{copy}</li>)}</ul>}
    {item.after?.map((copy) => <p key={copy}>{copy}</p>)}
    {item.secondaryBullets && <ul>{item.secondaryBullets.map((copy) => <li key={copy}>{copy}</li>)}</ul>}
    {item.final?.map((copy) => <p key={copy}>{copy}</p>)}
  </section>)}</div>;
}

function LegalFooter() {
  return <footer className="legal-footer"><span>© 2026 {legalConfig.projectName}</span><span className="legal-review-word">{legalConfig.paymentReviewWord}</span><nav><a href="#privacy">Конфиденциальность</a><a href="#terms">Соглашение</a><a href="#contacts">Контакты</a></nav></footer>;
}
