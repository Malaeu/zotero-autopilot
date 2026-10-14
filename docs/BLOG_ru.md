# Zotero на автопилоте: как заставить локальный API писать, а «Volltext finden» — находить

*14 октября 2026. Linux, Zotero 10.0.3 (flatpak), сеть университета. Всё ниже проверено на живой библиотеке; шаги воспроизводимы на macOS с поправкой на пути.*

Задача была простая и типичная: готовлю доклад по 38 статьям. Хочу, чтобы все статьи, их PDF и теги лежали в отдельной коллекции Zotero, и чтобы это делал агент, а не я руками. Выяснилось, что у Zotero для этого есть всё, но половина не задокументирована, а вторая половина сломана тихо, без сообщений об ошибке.

Ниже четыре проблемы и четыре решения.

---

## 1. Локальный API Zotero умеет писать, просто не говорит об этом

Zotero слушает `http://127.0.0.1:23119`. В документации описано чтение: `GET /api/users/0/collections`, `GET /api/users/0/items`. Любой `POST` отвечает `428 Precondition Required`, и большинство людей на этом останавливается.

Я распаковал исходники прямо из установленного пакета и прочитал шапку файла `server_localAPI.js`:

```bash
unzip -o /var/lib/flatpak/app/org.zotero.Zotero/current/active/files/share/zotero/app/omni.ja \
  'chrome/content/zotero/xpcom/server/*' -d /tmp/zot
sed -n 30,95p /tmp/zot/chrome/content/zotero/xpcom/server/server_localAPI.js
```

Там написано открытым текстом: запись поддерживается в объёме web API v3, нужны два заголовка.

**Шаг 1. Узнать Zotero-Server-ID.** Он приходит в любом ответе:

```bash
curl -s -D - -o /dev/null "http://127.0.0.1:23119/api/users/0/collections?limit=1" | grep -i Zotero-Server-ID
```

**Шаг 2. Получить ключ.** Один раз, с подтверждением в окне Zotero:

```bash
curl -s -X POST -H "Content-Type: application/json" \
  -H "Zotero-Server-ID: <ID из шага 1>" \
  -d '{"appName":"Мой скрипт"}' \
  http://127.0.0.1:23119/api/local/authorize
```

В Zotero появится диалог с тремя кнопками. Нажимать **«Always Allow»**. Кнопка «Allow» даёт одноразовый ключ, который сгорает после первой записи. Ответ: `{"key":"…32 символа…","remember":true}`. Ключ и Server-ID кладём в переменные окружения, например в `~/.api_keys`:

```bash
export ZOTERO_LOCAL_API_KEY=…
export ZOTERO_SERVER_ID=…
```

**Шаг 3. Писать.** Каждый запрос на запись несёт `Zotero-API-Key`, `Zotero-Server-ID` и версию библиотеки:

```bash
V=$(curl -s -D - -o /dev/null "http://127.0.0.1:23119/api/users/0/items?limit=1" | grep -i Last-Modified-Version | awk '{print $2}' | tr -d '\r')
curl -s -X POST "http://127.0.0.1:23119/api/users/0/items" \
  -H "Zotero-API-Key: $ZOTERO_LOCAL_API_KEY" -H "Zotero-Server-ID: $ZOTERO_SERVER_ID" \
  -H "If-Unmodified-Since-Version: $V" -H "Content-Type: application/json" \
  -d '[{"itemType":"journalArticle","title":"Test","DOI":"10.1000/xyz","collections":["<KEY коллекции>"],"tags":[{"tag":"projekt"}]}]'
```

Работает создание, `PATCH` полей и тегов, `DELETE ?itemKey=A,B` и загрузка файлов.

**Шаг 4. Загрузить PDF.** Три запроса, как в web API:

1. Создать дочернюю запись-вложение: `{"itemType":"attachment","linkMode":"imported_file","parentItem":"<KEY>","filename":"x.pdf","contentType":"application/pdf"}`.
2. `POST /api/users/0/items/<ATT>/file` с формой `md5, filename, filesize, mtime, contentType` и заголовком `If-None-Match: *`. Ответ содержит `url` и `uploadKey`.
3. Отправить сырые байты PDF на этот `url`, затем снова `POST …/file` с формой `upload=<uploadKey>` и `If-None-Match: *`. Ответ `204`, файл лежит в хранилище Zotero.

Клиент на чистом Python, без зависимостей, у меня лежит в `~/.claude/bin/zotero_local.py`. Методы: `create_items`, `patch_item`, `delete_items`, `upload_file`.

**Побочный бонус.** Коллекцию можно создать без API через Better BibTeX: `POST /better-bibtex/json-rpc` с методом `collection.scanAUX("/Meine Bibliothek/Имя", "/путь/к/пустому.aux")`. Пустой `.aux` файл, а коллекция создаётся.

---

## 2. Почему «Volltext finden» ничего не находит

«Volltext finden» делает три вещи: идёт на страницу DOI и ищет ссылку на PDF, спрашивает Unpaywall, спрашивает пользовательские резолверы из скрытой настройки `extensions.zotero.findPDFs.resolvers`.

Я проверил издателей из сети университета с лицензией. JAMA, Sage, Wiley, RSNA, OUP, BMJ, Ovid: всем не-браузерным клиентам они отвечают `403` и страницей bot-check. Zotero для них не браузер. Поэтому платные статьи через «Volltext finden» не приходят никогда, независимо от лицензии. Это не настройка, это защита издателей.

---

## 3. Резолверы: сломанный селектор и забаненный агент

В настройке `findPDFs.resolvers` у меня давно стоял Sci-Hub с селектором `#pdf` и атрибутом `src`. Zotero молчал: «Keine Datei gefunden». Два дефекта:

**Дефект 1, вёрстка.** sci-hub.ee сейчас отдаёт PDF в `<iframe src="…">`, элемента `#pdf` на странице больше нет. Селектор надо заменить на `iframe`.

**Дефект 2, user-agent.** Zotero представляется как `… Firefox/140.0 Zotero/10.0.3`. Cloudflare на зеркале режет любой агент со словом `Zotero/`. Проверка в три строки:

```bash
D=10.7326/0003-4819-101-5-692
curl -s -o /dev/null -w "%{http_code}\n" -A "Mozilla/5.0 (X11; Linux x86_64; rv:140.0) Gecko/20100101 Firefox/140.0 Zotero/10.0.3" "https://sci-hub.ee/$D"   # 403
curl -s -o /dev/null -w "%{http_code}\n" -A "Mozilla/5.0 (X11; Linux x86_64; rv:140.0) Gecko/20100101 Firefox/140.0" "https://sci-hub.ee/$D"                 # 200
```

Резолвер не задаёт свой агент, значит помогает только глобальная настройка Gecko. Обе правки делаются в `prefs.js` профиля при закрытом Zotero (Linux: `~/.zotero/zotero/<профиль>/prefs.js`; macOS: `~/Library/Application Support/Zotero/Profiles/<профиль>/prefs.js`):

```js
user_pref("extensions.zotero.findPDFs.resolvers", "[{\"name\":\"Sci-Hub (iframe)\",\"method\":\"GET\",\"url\":\"https://sci-hub.ee/{doi}\",\"mode\":\"html\",\"selector\":\"iframe\",\"attribute\":\"src\",\"automatic\":true},{\"name\":\"Unpaywall alle Orte\",\"method\":\"GET\",\"url\":\"https://api.unpaywall.org/v2/{doi}?email=nodp53@gmail.com\",\"mode\":\"json\",\"selector\":\".oa_locations\",\"mappings\":{\"url\":\"url_for_pdf\",\"pageURL\":\"url_for_landing_page\"},\"automatic\":true}]");
user_pref("general.useragent.override", "Mozilla/5.0 (X11; Linux x86_64; rv:140.0) Gecko/20100101 Firefox/140.0");
```

Перед правкой сделать копию `prefs.js`. После запуска Zotero: правый клик на записи без PDF → «Volltext finden». Для старых платных статей файл приходит за секунды. Для статей после 2022 года Sci-Hub пуст, это ограничение источника, не настройки.

Что не сработало и почему: `annas-archive.org` в университетской сети не резолвится по DNS, зеркало `.li` рисует страницу JavaScript-ом, а Zotero JS не выполняет. `libgen.im` не ищет по DOI, его форма ведёт на книжный поиск по словам. Как резолверы они бесполезны.

Юридическая оговорка: Sci-Hub в большинстве юрисдикций нарушает авторское право издателей. Это ваша настройка и ваша ответственность. Для лицензированного доступа есть путь из раздела 4.

---

## 4. PDF из-под лицензии без рук: свой Chrome по DevTools-протоколу

Если нужен PDF издателя по подписке, единственный клиент, который пропускают, это настоящий браузер. Я написал маленький Node-скрипт `cdp_pdf.js`: он поднимает Chrome с отдельным профилем, открывает URL и перехватывает ответ с `Content-Type: application/pdf` на стадии ответа через `Fetch.enable`, до того как встроенный просмотрщик Chrome его проглотит.

```bash
node ~/.claude/bin/cdp_pdf.js "https://www.thelancet.com/action/showPdf?pii=S0140-6736(26)01763-0" Omar_2026.pdf
node ~/.claude/bin/cdp_pdf.js "https://pmc.ncbi.nlm.nih.gov/articles/PMC1003190/pdf/x.pdf" Peterson_1992.pdf --headful
```

Главная тонкость: `Network.getResponseBody` для PDF возвращает заглушку в 536 байт, потому что тело уже забрал просмотрщик. Перехват через `Fetch.requestPaused` на `requestStage: "Response"` и `Fetch.getResponseBody` отдаёт настоящие байты. Сайты с Cloudflare Turnstile (bmj.com, sagepub.com) этот путь не проходит; там остаётся залогиненный браузер пользователя.

Для JAMA есть свой трюк: открыть ссылку вида `…/articlepdf/…pdf`, подождать шесть секунд, пока произойдёт редирект на `watermark*.silverchair.com`, и уже на этой странице выполнить `fetch(location.href)`.

---

## Что в итоге

Скрипт синхронизации (`zotero_sync.py`) за один прогон: удаляет лишние записи, создаёт недостающие по DOI из Crossref, ставит теги по схеме `ПРОЕКТ`, `ПРОЕКТ:folie:03`, `ПРОЕКТ:block:…`, `ПРОЕКТ:rolle:kern|kontext|reserve`, `ПРОЕКТ:pdf:attached|missing`, `ПРОЕКТ:fulltext:read|abstract:only`, и прикладывает все PDF из папки. Повторный запуск ничего не дублирует. 34 из 38 статей получили PDF автоматически, оставшиеся четыре закрыты Turnstile или не существуют онлайн.

Время на разбор: около трёх часов. Время на повтор для следующего проекта: минуты.

---

## Промт для агента Claude Code

Скопируй целиком в новую сессию Claude Code на машине, где установлен Zotero 7 или новее.

```text
Задача: настроить Zotero на этой машине для автоматической работы агента и проверить каждый шаг. Ничего не считай сделанным без проверки командой. Отчёт по-русски, короткими предложениями, с результатом каждой проверки.

Контекст: Zotero ≥ 7 установлен и запущен, локальный API слушает http://127.0.0.1:23119. Операционная система: определи сам (Linux или macOS). Пути профиля Zotero: Linux ~/.zotero/zotero/*/prefs.js, macOS ~/Library/Application Support/Zotero/Profiles/*/prefs.js.

Шаг 1. Проверь, что локальный API отвечает: GET http://127.0.0.1:23119/api/users/0/collections. Если нет, скажи пользователю включить в Zotero: Einstellungen → Erweitert → «Anderen Anwendungen auf diesem Computer erlauben, mit Zotero zu kommunizieren», и повтори.

Шаг 2. Получи Zotero-Server-ID из заголовка ответа любого GET-запроса. Запроси ключ записи: POST /api/local/authorize с JSON {"appName":"Claude Code"} и заголовком Zotero-Server-ID. Сообщи пользователю, что в Zotero откроется окно, и что нажимать нужно «Always Allow», иначе ключ одноразовый. Дождись ответа, проверь поле "remember": true. Сохрани ключ и Server-ID в файл с переменными окружения, который пользователь укажет (по умолчанию ~/.api_keys), как ZOTERO_LOCAL_API_KEY и ZOTERO_SERVER_ID. Ключ в чат не печатай.

Шаг 3. Напиши клиент на Python без внешних зависимостей, файл zotero_local.py, с функциями: get(path), create_items(list), patch_item(key, fields), delete_items(keys), upload_file(parent_key, path). Правила: каждый запрос на запись несёт заголовки Zotero-API-Key и Zotero-Server-ID; create и delete несут If-Unmodified-Since-Version равный заголовку Last-Modified-Version из GET /items?limit=1; PATCH несёт версию самой записи; не больше 50 объектов за запрос. upload_file: создать дочернее вложение linkMode imported_file с parentItem, filename, contentType; POST /items/<att>/file с формой md5, filename, filesize, mtime, contentType и заголовком If-None-Match: *; получить url и uploadKey; POST сырые байты на url; затем POST /items/<att>/file с формой upload=<uploadKey> и If-None-Match: *; ожидать 204.

Шаг 4. Проверь клиент на живой библиотеке: создай коллекцию «API-Test <дата>» (через Better BibTeX JSON-RPC collection.scanAUX с пустым .aux, если BBT установлен, иначе через POST /api/users/0/collections), создай в ней одну тестовую запись journalArticle с DOI 10.7326/0003-4819-101-5-692 и тегом test:api, поставь ей ещё один тег через patch_item, загрузи любой маленький PDF через upload_file, прочитай /items/<key>/children и убедись, что вложение есть. Покажи пользователю результат. Удали тестовую запись только после его слова.

Шаг 5. Диагностика «Volltext finden». Прочитай из prefs.js значения extensions.zotero.findPDFs.resolvers и general.useragent.override. Для каждого резолвера сделай curl на его URL с DOI 10.7326/0003-4819-101-5-692 дважды: с агентом, содержащим «Zotero/», и с чистым агентом Firefox. Сравни коды ответов. Проверь, присутствует ли на странице элемент из селектора резолвера. Выведи таблицу: резолвер, код с Zotero-агентом, код с Firefox-агентом, найден ли селектор.

Шаг 6. Если резолвер блокирует агент «Zotero/» или селектор устарел, предложи пользователю точные правки prefs.js: новый JSON резолверов и строку general.useragent.override с чистым Firefox-агентом. Объясни, что Sci-Hub находится в правовой серой зоне и решение принимает пользователь. Вноси правки только при закрытом Zotero и только после слова пользователя; перед правкой сделай копию prefs.js с датой. После запуска Zotero попроси пользователя выполнить «Volltext finden» на тестовой записи и сообщить результат.

Шаг 7. Напиши для проекта пользователя скрипт zotero_sync.py: принимает папку с PDF и таблицу DOI → (имя файла, список слайдов или разделов, блок, роль), ставит теги по схеме ПРОЕКТ, ПРОЕКТ:folie:NN, ПРОЕКТ:block:…, ПРОЕКТ:rolle:kern|kontext|reserve, ПРОЕКТ:pdf:attached|missing, ПРОЕКТ:fulltext:read|abstract:only, прикладывает PDF, если у записи ещё нет вложения, и ничего не дублирует при повторном запуске. Прогони его дважды и покажи, что второй прогон ничего не изменил.

Шаг 8. Итоговый отчёт: что проверено командой и каким выводом, что осталось открытым, какие файлы созданы, с абсолютными путями. Не утверждай «работает» для шагов, которые не прошли проверку.
```
