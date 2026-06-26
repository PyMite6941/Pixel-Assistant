"""
Language learning & translation skill.

Modes
-----
Online  — LLM-powered rich translation with grammar notes, pronunciation,
          and contextual examples.  Full language-tutor lessons via the LLM.
Offline — argostranslate package (pip install argostranslate) + built-in
          static vocabulary packs for 12 languages stored locally in JSON.

Data stored in: functionalities/language_progress.json
Offline packs:  argostranslate manages its own directory (~/.argos-translate)
"""
from __future__ import annotations

import json
import random
from datetime import date, datetime
from pathlib import Path

# ── Paths ─────────────────────────────────────────────────────────────────────

_BASE       = Path(__file__).parent.parent / "functionalities"
_PROGRESS   = _BASE / "language_progress.json"

# ── ISO 639-1 map used for argostranslate lookup ──────────────────────────────

LANG_CODE: dict[str, str] = {
    "spanish":    "es", "español":   "es",
    "french":     "fr", "français":  "fr",
    "german":     "de", "deutsch":   "de",
    "italian":    "it", "italiano":  "it",
    "portuguese": "pt",
    "russian":    "ru",
    "japanese":   "ja",
    "korean":     "ko",
    "chinese":    "zh", "mandarin":  "zh",
    "arabic":     "ar",
    "hindi":      "hi",
    "dutch":      "nl",
    "polish":     "pl",
    "turkish":    "tr",
    "swedish":    "sv",
    "norwegian":  "no",
    "danish":     "da",
    "english":    "en",
}

# ── Static vocabulary packs (built-in, no download needed) ───────────────────

VOCAB: dict[str, dict[str, list[tuple[str, str]]]] = {
    "es": {
        "greetings": [
            ("hello", "hola"), ("goodbye", "adiós"), ("good morning", "buenos días"),
            ("good night", "buenas noches"), ("please", "por favor"), ("thank you", "gracias"),
            ("you're welcome", "de nada"), ("sorry", "lo siento"), ("yes", "sí"), ("no", "no"),
            ("how are you?", "¿cómo estás?"), ("I'm fine", "estoy bien"),
            ("what is your name?", "¿cómo te llamas?"), ("my name is", "me llamo"),
        ],
        "numbers": [
            ("one", "uno"), ("two", "dos"), ("three", "tres"), ("four", "cuatro"),
            ("five", "cinco"), ("six", "seis"), ("seven", "siete"), ("eight", "ocho"),
            ("nine", "nueve"), ("ten", "diez"), ("twenty", "veinte"), ("hundred", "cien"),
        ],
        "phrases": [
            ("where is the bathroom?", "¿dónde está el baño?"),
            ("I don't understand", "no entiendo"), ("speak slowly please", "habla más despacio por favor"),
            ("how much does it cost?", "¿cuánto cuesta?"), ("help!", "¡ayuda!"),
            ("I am hungry", "tengo hambre"), ("I am thirsty", "tengo sed"),
            ("I love you", "te quiero"),
        ],
        "days": [
            ("Monday", "lunes"), ("Tuesday", "martes"), ("Wednesday", "miércoles"),
            ("Thursday", "jueves"), ("Friday", "viernes"), ("Saturday", "sábado"), ("Sunday", "domingo"),
        ],
        "colors": [
            ("red", "rojo"), ("blue", "azul"), ("green", "verde"), ("yellow", "amarillo"),
            ("black", "negro"), ("white", "blanco"), ("orange", "naranja"), ("purple", "morado"),
        ],
    },
    "fr": {
        "greetings": [
            ("hello", "bonjour"), ("goodbye", "au revoir"), ("good morning", "bonjour"),
            ("good night", "bonne nuit"), ("please", "s'il vous plaît"), ("thank you", "merci"),
            ("you're welcome", "de rien"), ("sorry", "désolé"), ("yes", "oui"), ("no", "non"),
            ("how are you?", "comment allez-vous?"), ("I'm fine", "je vais bien"),
            ("what is your name?", "comment vous appelez-vous?"), ("my name is", "je m'appelle"),
        ],
        "numbers": [
            ("one", "un"), ("two", "deux"), ("three", "trois"), ("four", "quatre"),
            ("five", "cinq"), ("six", "six"), ("seven", "sept"), ("eight", "huit"),
            ("nine", "neuf"), ("ten", "dix"), ("twenty", "vingt"), ("hundred", "cent"),
        ],
        "phrases": [
            ("where is the bathroom?", "où sont les toilettes?"),
            ("I don't understand", "je ne comprends pas"), ("speak slowly please", "parlez lentement s'il vous plaît"),
            ("how much does it cost?", "combien ça coûte?"), ("help!", "au secours!"),
            ("I am hungry", "j'ai faim"), ("I am thirsty", "j'ai soif"),
            ("I love you", "je t'aime"),
        ],
        "days": [
            ("Monday", "lundi"), ("Tuesday", "mardi"), ("Wednesday", "mercredi"),
            ("Thursday", "jeudi"), ("Friday", "vendredi"), ("Saturday", "samedi"), ("Sunday", "dimanche"),
        ],
        "colors": [
            ("red", "rouge"), ("blue", "bleu"), ("green", "vert"), ("yellow", "jaune"),
            ("black", "noir"), ("white", "blanc"), ("orange", "orange"), ("purple", "violet"),
        ],
    },
    "de": {
        "greetings": [
            ("hello", "hallo"), ("goodbye", "auf Wiedersehen"), ("good morning", "guten Morgen"),
            ("good night", "gute Nacht"), ("please", "bitte"), ("thank you", "danke"),
            ("you're welcome", "bitte sehr"), ("sorry", "entschuldigung"), ("yes", "ja"), ("no", "nein"),
            ("how are you?", "wie geht es Ihnen?"), ("I'm fine", "mir geht es gut"),
            ("what is your name?", "wie heißen Sie?"), ("my name is", "ich heiße"),
        ],
        "numbers": [
            ("one", "eins"), ("two", "zwei"), ("three", "drei"), ("four", "vier"),
            ("five", "fünf"), ("six", "sechs"), ("seven", "sieben"), ("eight", "acht"),
            ("nine", "neun"), ("ten", "zehn"), ("twenty", "zwanzig"), ("hundred", "hundert"),
        ],
        "phrases": [
            ("where is the bathroom?", "wo ist die Toilette?"),
            ("I don't understand", "ich verstehe nicht"), ("speak slowly please", "sprechen Sie bitte langsam"),
            ("how much does it cost?", "wie viel kostet das?"), ("help!", "Hilfe!"),
            ("I am hungry", "ich habe Hunger"), ("I am thirsty", "ich habe Durst"),
            ("I love you", "ich liebe dich"),
        ],
        "days": [
            ("Monday", "Montag"), ("Tuesday", "Dienstag"), ("Wednesday", "Mittwoch"),
            ("Thursday", "Donnerstag"), ("Friday", "Freitag"), ("Saturday", "Samstag"), ("Sunday", "Sonntag"),
        ],
        "colors": [
            ("red", "rot"), ("blue", "blau"), ("green", "grün"), ("yellow", "gelb"),
            ("black", "schwarz"), ("white", "weiß"), ("orange", "orange"), ("purple", "lila"),
        ],
    },
    "ja": {
        "greetings": [
            ("hello", "こんにちは (konnichiwa)"), ("goodbye", "さようなら (sayounara)"),
            ("good morning", "おはよう (ohayou)"), ("good night", "おやすみ (oyasumi)"),
            ("please", "おねがい (onegai)"), ("thank you", "ありがとう (arigatou)"),
            ("you're welcome", "どういたしまして (dou itashimashite)"), ("sorry", "ごめんなさい (gomen nasai)"),
            ("yes", "はい (hai)"), ("no", "いいえ (iie)"),
            ("how are you?", "おげんきですか？(ogenki desuka?)"), ("I'm fine", "げんきです (genki desu)"),
            ("what is your name?", "おなまえは？(onamae wa?)"), ("my name is", "わたしのなまえは (watashi no namae wa)"),
        ],
        "numbers": [
            ("one", "いち (ichi)"), ("two", "に (ni)"), ("three", "さん (san)"), ("four", "し (shi)"),
            ("five", "ご (go)"), ("six", "ろく (roku)"), ("seven", "なな (nana)"), ("eight", "はち (hachi)"),
            ("nine", "きゅう (kyuu)"), ("ten", "じゅう (juu)"),
        ],
        "phrases": [
            ("where is the bathroom?", "トイレはどこですか？(toire wa doko desuka?)"),
            ("I don't understand", "わかりません (wakarimasen)"),
            ("how much does it cost?", "いくらですか？(ikura desuka?)"),
            ("help!", "たすけて！(tasukete!)"), ("I am hungry", "おなかがすいた (onaka ga suita)"),
        ],
        "days": [
            ("Monday", "月曜日 (getsuyoubi)"), ("Tuesday", "火曜日 (kayoubi)"),
            ("Wednesday", "水曜日 (suiyoubi)"), ("Thursday", "木曜日 (mokuyoubi)"),
            ("Friday", "金曜日 (kinyoubi)"), ("Saturday", "土曜日 (doyoubi)"), ("Sunday", "日曜日 (nichiyoubi)"),
        ],
        "colors": [
            ("red", "赤 (aka)"), ("blue", "青 (ao)"), ("green", "緑 (midori)"), ("yellow", "黄色 (kiiro)"),
            ("black", "黒 (kuro)"), ("white", "白 (shiro)"),
        ],
    },
    "ko": {
        "greetings": [
            ("hello", "안녕하세요 (annyeonghaseyo)"), ("goodbye", "안녕히 가세요 (annyeonghi gaseyo)"),
            ("thank you", "감사합니다 (gamsahamnida)"), ("sorry", "죄송합니다 (joesonghamnida)"),
            ("yes", "네 (ne)"), ("no", "아니요 (aniyo)"),
            ("how are you?", "잘 지내세요? (jal jinaeseyo?)"), ("I'm fine", "잘 지냅니다 (jal jinaemnida)"),
        ],
        "numbers": [
            ("one", "일 (il)"), ("two", "이 (i)"), ("three", "삼 (sam)"), ("four", "사 (sa)"),
            ("five", "오 (o)"), ("six", "육 (yuk)"), ("seven", "칠 (chil)"), ("eight", "팔 (pal)"),
            ("nine", "구 (gu)"), ("ten", "십 (sip)"),
        ],
        "phrases": [
            ("where is the bathroom?", "화장실이 어디예요? (hwajangsiri eodiyeyo?)"),
            ("I don't understand", "모르겠어요 (moreugesseoyo)"),
            ("how much does it cost?", "얼마예요? (eolmayeyo?)"), ("help!", "도와주세요! (dowajuseyo!)"),
        ],
        "days": [
            ("Monday", "월요일 (woryoil)"), ("Tuesday", "화요일 (hwayoil)"),
            ("Wednesday", "수요일 (suyoil)"), ("Thursday", "목요일 (mogyoil)"),
            ("Friday", "금요일 (geumyoil)"), ("Saturday", "토요일 (toyoil)"), ("Sunday", "일요일 (iryoil)"),
        ],
        "colors": [
            ("red", "빨간색 (ppalganssaek)"), ("blue", "파란색 (paranssaek)"),
            ("green", "초록색 (choroksaek)"), ("yellow", "노란색 (noranssaek)"),
            ("black", "검은색 (geomeunsaek)"), ("white", "흰색 (hinsaek)"),
        ],
    },
    "it": {
        "greetings": [
            ("hello", "ciao"), ("goodbye", "arrivederci"), ("good morning", "buongiorno"),
            ("good night", "buonanotte"), ("please", "per favore"), ("thank you", "grazie"),
            ("you're welcome", "prego"), ("sorry", "mi dispiace"), ("yes", "sì"), ("no", "no"),
            ("how are you?", "come stai?"), ("I'm fine", "sto bene"),
        ],
        "numbers": [
            ("one", "uno"), ("two", "due"), ("three", "tre"), ("four", "quattro"),
            ("five", "cinque"), ("six", "sei"), ("seven", "sette"), ("eight", "otto"),
            ("nine", "nove"), ("ten", "dieci"),
        ],
        "phrases": [
            ("where is the bathroom?", "dov'è il bagno?"), ("I don't understand", "non capisco"),
            ("how much does it cost?", "quanto costa?"), ("help!", "aiuto!"),
            ("I am hungry", "ho fame"), ("I love you", "ti amo"),
        ],
        "days": [
            ("Monday", "lunedì"), ("Tuesday", "martedì"), ("Wednesday", "mercoledì"),
            ("Thursday", "giovedì"), ("Friday", "venerdì"), ("Saturday", "sabato"), ("Sunday", "domenica"),
        ],
        "colors": [
            ("red", "rosso"), ("blue", "blu"), ("green", "verde"), ("yellow", "giallo"),
            ("black", "nero"), ("white", "bianco"),
        ],
    },
    "pt": {
        "greetings": [
            ("hello", "olá"), ("goodbye", "tchau"), ("good morning", "bom dia"),
            ("good night", "boa noite"), ("please", "por favor"), ("thank you", "obrigado/a"),
            ("sorry", "desculpe"), ("yes", "sim"), ("no", "não"),
            ("how are you?", "como vai você?"), ("I'm fine", "estou bem"),
        ],
        "numbers": [
            ("one", "um"), ("two", "dois"), ("three", "três"), ("four", "quatro"),
            ("five", "cinco"), ("six", "seis"), ("seven", "sete"), ("eight", "oito"),
            ("nine", "nove"), ("ten", "dez"),
        ],
        "phrases": [
            ("where is the bathroom?", "onde fica o banheiro?"), ("I don't understand", "não entendo"),
            ("how much does it cost?", "quanto custa?"), ("help!", "socorro!"), ("I love you", "eu te amo"),
        ],
        "days": [
            ("Monday", "segunda-feira"), ("Tuesday", "terça-feira"), ("Wednesday", "quarta-feira"),
            ("Thursday", "quinta-feira"), ("Friday", "sexta-feira"), ("Saturday", "sábado"), ("Sunday", "domingo"),
        ],
        "colors": [
            ("red", "vermelho"), ("blue", "azul"), ("green", "verde"), ("yellow", "amarelo"),
            ("black", "preto"), ("white", "branco"),
        ],
    },
    "ru": {
        "greetings": [
            ("hello", "привет (privet)"), ("goodbye", "до свидания (do svidaniya)"),
            ("good morning", "доброе утро (dobroye utro)"), ("good night", "спокойной ночи (spokoinoy nochi)"),
            ("please", "пожалуйста (pozhaluysta)"), ("thank you", "спасибо (spasibo)"),
            ("sorry", "извините (izvinite)"), ("yes", "да (da)"), ("no", "нет (nyet)"),
            ("how are you?", "как дела? (kak dela?)"), ("I'm fine", "всё хорошо (vsyo khorosho)"),
        ],
        "numbers": [
            ("one", "один (odin)"), ("two", "два (dva)"), ("three", "три (tri)"),
            ("four", "четыре (chetyre)"), ("five", "пять (pyat)"),
            ("six", "шесть (shest)"), ("seven", "семь (sem)"), ("eight", "восемь (vosem)"),
            ("nine", "девять (devyat)"), ("ten", "десять (desyat)"),
        ],
        "phrases": [
            ("where is the bathroom?", "где туалет? (gde tualet?)"),
            ("I don't understand", "я не понимаю (ya ne ponimayu)"),
            ("how much does it cost?", "сколько стоит? (skolko stoit?)"),
            ("help!", "помогите! (pomogite!)"), ("I love you", "я тебя люблю (ya tebya lyublyu)"),
        ],
        "days": [
            ("Monday", "понедельник (ponedelnik)"), ("Tuesday", "вторник (vtornik)"),
            ("Wednesday", "среда (sreda)"), ("Thursday", "четверг (chetverg)"),
            ("Friday", "пятница (pyatnitsa)"), ("Saturday", "суббота (subbota)"), ("Sunday", "воскресенье (voskresenye)"),
        ],
        "colors": [
            ("red", "красный (krasny)"), ("blue", "синий (siniy)"), ("green", "зелёный (zelyony)"),
            ("yellow", "жёлтый (zholty)"), ("black", "чёрный (chorny)"), ("white", "белый (bely)"),
        ],
    },
    "zh": {
        "greetings": [
            ("hello", "你好 (nǐ hǎo)"), ("goodbye", "再见 (zàijiàn)"),
            ("good morning", "早上好 (zǎoshang hǎo)"), ("good night", "晚安 (wǎn'ān)"),
            ("please", "请 (qǐng)"), ("thank you", "谢谢 (xièxiè)"),
            ("you're welcome", "不客气 (bù kèqi)"), ("sorry", "对不起 (duìbuqǐ)"),
            ("yes", "是 (shì)"), ("no", "不 (bù)"),
            ("how are you?", "你好吗？(nǐ hǎo ma?)"), ("I'm fine", "我很好 (wǒ hěn hǎo)"),
        ],
        "numbers": [
            ("one", "一 (yī)"), ("two", "二 (èr)"), ("three", "三 (sān)"), ("four", "四 (sì)"),
            ("five", "五 (wǔ)"), ("six", "六 (liù)"), ("seven", "七 (qī)"), ("eight", "八 (bā)"),
            ("nine", "九 (jiǔ)"), ("ten", "十 (shí)"),
        ],
        "phrases": [
            ("where is the bathroom?", "厕所在哪里？(cèsuǒ zài nǎlǐ?)"),
            ("I don't understand", "我不明白 (wǒ bù míngbái)"),
            ("how much does it cost?", "多少钱？(duōshǎo qián?)"),
            ("help!", "救命！(jiùmìng!)"), ("I love you", "我爱你 (wǒ ài nǐ)"),
        ],
        "days": [
            ("Monday", "星期一 (xīngqī yī)"), ("Tuesday", "星期二 (xīngqī èr)"),
            ("Wednesday", "星期三 (xīngqī sān)"), ("Thursday", "星期四 (xīngqī sì)"),
            ("Friday", "星期五 (xīngqī wǔ)"), ("Saturday", "星期六 (xīngqī liù)"), ("Sunday", "星期日 (xīngqī rì)"),
        ],
        "colors": [
            ("red", "红色 (hóngsè)"), ("blue", "蓝色 (lánsè)"), ("green", "绿色 (lǜsè)"),
            ("yellow", "黄色 (huángsè)"), ("black", "黑色 (hēisè)"), ("white", "白色 (báisè)"),
        ],
    },
    "ar": {
        "greetings": [
            ("hello", "مرحبا (marhaba)"), ("goodbye", "مع السلامة (ma'a as-salama)"),
            ("good morning", "صباح الخير (sabah al-khayr)"), ("good night", "تصبح على خير (tusbih ala khayr)"),
            ("please", "من فضلك (min fadlik)"), ("thank you", "شكرا (shukran)"),
            ("sorry", "آسف (aasif)"), ("yes", "نعم (na'am)"), ("no", "لا (la)"),
            ("how are you?", "كيف حالك؟ (kayfa halak?)"), ("I'm fine", "أنا بخير (ana bekhayr)"),
        ],
        "numbers": [
            ("one", "واحد (wahid)"), ("two", "اثنان (ithnan)"), ("three", "ثلاثة (thalatha)"),
            ("four", "أربعة (arba'a)"), ("five", "خمسة (khamsa)"),
            ("six", "ستة (sitta)"), ("seven", "سبعة (sab'a)"), ("eight", "ثمانية (thamaniya)"),
            ("nine", "تسعة (tis'a)"), ("ten", "عشرة ('ashara)"),
        ],
        "phrases": [
            ("where is the bathroom?", "أين الحمام؟ (ayn al-hammam?)"),
            ("I don't understand", "لا أفهم (la afham)"),
            ("how much does it cost?", "كم يكلف؟ (kam yukalif?)"),
            ("help!", "مساعدة! (musa'ada!)"),
        ],
        "days": [
            ("Monday", "الاثنين (al-ithnayn)"), ("Tuesday", "الثلاثاء (ath-thulatha)"),
            ("Wednesday", "الأربعاء (al-arbi'a)"), ("Thursday", "الخميس (al-khamis)"),
            ("Friday", "الجمعة (al-jum'a)"), ("Saturday", "السبت (as-sabt)"), ("Sunday", "الأحد (al-ahad)"),
        ],
        "colors": [
            ("red", "أحمر (ahmar)"), ("blue", "أزرق (azraq)"), ("green", "أخضر (akhdar)"),
            ("yellow", "أصفر (asfar)"), ("black", "أسود (aswad)"), ("white", "أبيض (abyad)"),
        ],
    },
    "hi": {
        "greetings": [
            ("hello", "नमस्ते (namaste)"), ("goodbye", "अलविदा (alvida)"),
            ("good morning", "सुप्रभात (suprabhat)"), ("good night", "शुभ रात्रि (shubh ratri)"),
            ("please", "कृपया (kripaya)"), ("thank you", "धन्यवाद (dhanyavad)"),
            ("sorry", "माफ कीजिए (maaf kijiye)"), ("yes", "हाँ (haan)"), ("no", "नहीं (nahin)"),
            ("how are you?", "आप कैसे हैं? (aap kaise hain?)"), ("I'm fine", "मैं ठीक हूँ (main theek hoon)"),
        ],
        "numbers": [
            ("one", "एक (ek)"), ("two", "दो (do)"), ("three", "तीन (teen)"), ("four", "चार (char)"),
            ("five", "पाँच (paanch)"), ("six", "छह (chhah)"), ("seven", "सात (saat)"),
            ("eight", "आठ (aath)"), ("nine", "नौ (nau)"), ("ten", "दस (das)"),
        ],
        "phrases": [
            ("where is the bathroom?", "बाथरूम कहाँ है? (bathroom kahan hai?)"),
            ("I don't understand", "मुझे समझ नहीं आया (mujhe samajh nahin aaya)"),
            ("how much does it cost?", "इसकी कीमत क्या है? (iski keemat kya hai?)"),
            ("help!", "मदद करो! (madad karo!)"), ("I love you", "मैं तुमसे प्यार करता हूँ (main tumse pyar karta hoon)"),
        ],
        "days": [
            ("Monday", "सोमवार (somvar)"), ("Tuesday", "मंगलवार (mangalvar)"),
            ("Wednesday", "बुधवार (budhvar)"), ("Thursday", "गुरुवार (guruvar)"),
            ("Friday", "शुक्रवार (shukravar)"), ("Saturday", "शनिवार (shanivar)"), ("Sunday", "रविवार (ravivar)"),
        ],
        "colors": [
            ("red", "लाल (lal)"), ("blue", "नीला (neela)"), ("green", "हरा (hara)"),
            ("yellow", "पीला (peela)"), ("black", "काला (kala)"), ("white", "सफेद (safed)"),
        ],
    },
}

TOPICS = ["greetings", "numbers", "phrases", "days", "colors"]

# ── Progress persistence ───────────────────────────────────────────────────────

def _load_progress() -> dict:
    if _PROGRESS.exists():
        try:
            return json.loads(_PROGRESS.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _save_progress(data: dict):
    _BASE.mkdir(exist_ok=True)
    _PROGRESS.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _get_lang_progress(lang_code: str) -> dict:
    data = _load_progress()
    return data.get(lang_code, {
        "learned": [],          # list of english words marked learned
        "sessions": 0,
        "correct": 0,
        "total_drills": 0,
        "streak_today": 0,
        "last_session": "",
    })


def _update_lang_progress(lang_code: str, patch: dict):
    data = _load_progress()
    current = data.get(lang_code, {})
    current.update(patch)
    data[lang_code] = current
    _save_progress(data)


# ── Offline translation (argostranslate) ─────────────────────────────────────

def _argos_available() -> bool:
    try:
        import argostranslate.translate  # noqa
        return True
    except ImportError:
        return False


def _argos_installed_langs() -> list[str]:
    """Return list of (from_code, to_code) pairs that are installed."""
    try:
        import argostranslate.translate as _t
        return [f"{p.from_code}->{p.to_code}" for p in _t.get_installed_packages()]
    except Exception:
        return []


def translate_offline(text: str, to_lang: str, from_lang: str = "en") -> str | None:
    """Attempt offline translation via argostranslate. Returns None if not available."""
    if not _argos_available():
        return None
    to_code   = LANG_CODE.get(to_lang.lower(), to_lang.lower()[:2])
    from_code = LANG_CODE.get(from_lang.lower(), from_lang.lower()[:2])
    try:
        import argostranslate.translate as _t
        translated = _t.translate(text, from_code, to_code)
        return translated
    except Exception:
        return None


def download_offline_pack(lang: str) -> str:
    """Download argostranslate package for the given language (en ↔ lang)."""
    if not _argos_available():
        return (
            "argostranslate is not installed.\n"
            "Install it with:  pip install argostranslate\n"
            "Then run this command again to download the language pack."
        )
    code = LANG_CODE.get(lang.lower(), lang.lower()[:2])
    try:
        import argostranslate.package as _pkg
        import argostranslate.translate as _t

        print(f"Fetching available packages from argostranslate hub...")
        _pkg.update_package_index()
        available = _pkg.get_available_packages()

        en_to_lang = [p for p in available if p.from_code == "en" and p.to_code == code]
        lang_to_en = [p for p in available if p.from_code == code and p.to_code == "en"]

        if not en_to_lang and not lang_to_en:
            return (
                f"No offline package found for '{lang}' (code: {code}).\n"
                f"Available language codes: {', '.join(set(p.to_code for p in available[:30]))}"
            )

        installed = 0
        for pkg in (en_to_lang + lang_to_en):
            print(f"  Downloading {pkg.from_code} → {pkg.to_code} ({pkg.package_version})...")
            pkg.install()
            installed += 1

        return (
            f"Downloaded {installed} package(s) for {lang}.\n"
            f"Offline translation now available for English ↔ {lang}."
        )
    except Exception as e:
        return f"Download failed: {e}"


def check_offline_status() -> str:
    """Return a human-readable status of offline translation capability."""
    if not _argos_available():
        return (
            "Offline translation: NOT AVAILABLE\n"
            "Install:  pip install argostranslate\n"
            "Then:     /lang download <language>"
        )
    pairs = _argos_installed_langs()
    if not pairs:
        return (
            "argostranslate installed but no language packs downloaded yet.\n"
            "Use:  /lang download <language>  to add a language pack."
        )
    return "Offline translation available for:\n" + "\n".join(f"  {p}" for p in pairs)


# ── Vocabulary drill ──────────────────────────────────────────────────────────

def vocab_drill(lang: str, topic: str = "all", count: int = 8) -> tuple[list[tuple[str,str]], str]:
    """
    Return a list of (english, target) pairs for a drill session.
    topic: 'all' or one of TOPICS.
    Also returns the display name for the language.
    """
    code = LANG_CODE.get(lang.lower(), lang.lower()[:2])
    lang_data = VOCAB.get(code)
    if not lang_data:
        supported = ", ".join(k for k, v in LANG_CODE.items() if v in VOCAB)
        return [], f"No built-in vocabulary for '{lang}'. Supported: {supported}"

    pairs: list[tuple[str,str]] = []
    if topic == "all":
        for t in TOPICS:
            pairs.extend(lang_data.get(t, []))
    else:
        pairs.extend(lang_data.get(topic, []))

    if not pairs:
        return [], f"No vocabulary for topic '{topic}'."

    sample = random.sample(pairs, min(count, len(pairs)))
    return sample, code


def run_drill_session(lang: str, topic: str = "all", count: int = 8) -> str:
    """
    Interactive flashcard drill. Returns a summary string.
    Call this from main.py — it uses input() directly.
    """
    pairs, code = vocab_drill(lang, topic, count)
    if not pairs:
        return code  # error message

    lang_name = lang.capitalize()
    print(f"\n  Vocabulary drill — {lang_name}  ({topic})")
    print(f"  {len(pairs)} cards  |  Type the translation or '?' to reveal  |  'q' to quit\n")

    correct = 0
    seen = 0
    learned_today: list[str] = []

    for i, (english, target) in enumerate(pairs, 1):
        print(f"  [{i}/{len(pairs)}]  {english}")
        try:
            answer = input("  Your answer: ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if answer.lower() == "q":
            break
        if answer == "?":
            print(f"  => {target}")
            seen += 1
            continue
        # Check: strip romanization from target for comparison
        clean_target = target.split("(")[0].strip().lower().rstrip(".")
        if answer.lower() in (target.lower(), clean_target):
            print(f"  Correct! {target}")
            correct += 1
            learned_today.append(english)
        else:
            print(f"  Not quite. Answer: {target}")
        seen += 1

    # Update progress
    progress = _get_lang_progress(code)
    already_learned = set(progress.get("learned", []))
    new_learned = [w for w in learned_today if w not in already_learned]
    already_learned.update(new_learned)

    today = date.today().isoformat()
    streak = progress.get("streak_today", 0)
    if progress.get("last_session") == today:
        streak += 1
    else:
        streak = 1

    _update_lang_progress(code, {
        "learned": list(already_learned),
        "sessions": progress.get("sessions", 0) + 1,
        "correct": progress.get("correct", 0) + correct,
        "total_drills": progress.get("total_drills", 0) + seen,
        "streak_today": streak,
        "last_session": today,
    })

    pct = int(correct / seen * 100) if seen else 0
    return (
        f"\n  Drill complete!  {correct}/{seen} correct ({pct}%)\n"
        f"  New words learned: {len(new_learned)}  |  Total learned: {len(already_learned)}"
    )


# ── LLM-powered tutor lesson ──────────────────────────────────────────────────

def build_lesson_prompt(lang: str, topic: str, level: str = "beginner") -> str:
    """Build a detailed language tutor prompt for the LLM."""
    built_in = ""
    code = LANG_CODE.get(lang.lower(), "")
    if code and code in VOCAB and topic in VOCAB.get(code, {}):
        pairs = VOCAB[code][topic][:8]
        built_in = "\n\nBuilt-in vocabulary for reference:\n" + "\n".join(
            f"  {e} = {t}" for e, t in pairs
        )

    return (
        f"You are an expert language tutor teaching {lang} to a {level} English speaker.\n\n"
        f"Give a structured lesson on: {topic}\n"
        f"Level: {level}\n"
        f"{built_in}\n\n"
        "Your lesson must include ALL of these sections:\n\n"
        "## Vocabulary\n"
        "  List 8-12 key words/phrases with pronunciation guide in parentheses.\n\n"
        "## Grammar Note\n"
        "  Explain ONE key grammar rule relevant to this topic. Keep it simple.\n\n"
        "## Example Sentences\n"
        "  Show 4 natural example sentences with English translation.\n\n"
        "## Cultural Tip\n"
        "  One interesting cultural fact about how this topic is used.\n\n"
        "## Practice\n"
        "  Give 3 fill-in-the-blank exercises the learner can answer.\n\n"
        "Be encouraging, clear, and conversational. Use bold for target language words."
    )


def build_translation_prompt(text: str, to_lang: str, explain: bool = False) -> str:
    """Build an agent-quality translation prompt."""
    base = (
        f"Translate the following text into {to_lang}.\n\n"
        f"Text:\n{text}\n\n"
    )
    if explain:
        return base + (
            "Provide:\n"
            "1. **Translation** — the full translation\n"
            "2. **Pronunciation** — romanization/phonetics if not a Latin script\n"
            "3. **Word-by-word** — brief breakdown of key words (3-5 most important)\n"
            "4. **Alternative phrasing** — one more natural or formal alternative\n"
            "5. **Usage note** — one sentence about register (formal/casual/written/spoken)\n\n"
            "Format each section with a bold header."
        )
    return base + "Reply with ONLY the translation — no explanations, no original text."


def build_conversation_prompt(lang: str, scenario: str = "at a café") -> str:
    """Build a practice conversation prompt."""
    return (
        f"Create a short practice dialogue in {lang} for this scenario: {scenario}\n\n"
        "Format:\n"
        "- 6-8 exchanges (Person A / Person B)\n"
        "- Each line: target language  /  English in parentheses\n"
        "- Mark difficult words with *asterisks*\n"
        "- After the dialogue, list 5 key vocabulary items from it\n"
        "- End with a TIP about something specific to this scenario in {lang} culture"
    )


# ── Progress report ───────────────────────────────────────────────────────────

def progress_report() -> str:
    data = _load_progress()
    if not data:
        return "No language learning progress yet. Start with: /lang learn <language>"

    reverse_code = {v: k.capitalize() for k, v in LANG_CODE.items()}
    lines = ["Language Learning Progress\n"]
    for code, stats in data.items():
        name = reverse_code.get(code, code.upper())
        learned = len(stats.get("learned", []))
        sessions = stats.get("sessions", 0)
        correct  = stats.get("correct", 0)
        total    = stats.get("total_drills", 0)
        pct      = int(correct / total * 100) if total else 0
        streak   = stats.get("streak_today", 0)
        lines.append(
            f"  {name:<14} words learned: {learned:<5} sessions: {sessions:<5} "
            f"accuracy: {pct}%  streak: {streak}"
        )
    return "\n".join(lines)
