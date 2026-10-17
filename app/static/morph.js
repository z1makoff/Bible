// Расшифровка морфологических кодов OSHB простыми русскими словами.
// Коды — аннотация OSHB, а не часть текста; см. hb.openscriptures.org/parsing.
"use strict";

const MORPH = (() => {
  const STEMS_H = {
    q: "qal (простая)", N: "niphal", p: "piel", P: "pual", h: "hiphil", H: "hophal", t: "hithpael",
    o: "polel", O: "polal", r: "hithpolel", m: "poel", M: "poal", k: "palel", K: "pulal",
    Q: "qal страдательная", l: "pilpel", L: "polpal", f: "hithpalpel", D: "nithpael", j: "pealal",
    i: "pilel", u: "hothpaal", c: "tiphil", v: "hishtaphel", w: "nithpalel", y: "nithpoel", z: "hithpoel",
  };
  const STEMS_A = {
    q: "peal (простая)", Q: "peil", u: "hithpeel", p: "pael", P: "ithpaal", M: "hithpaal", a: "aphel",
    h: "haphel", s: "saphel", e: "shaphel", H: "hophal", i: "ithpeel", t: "hishtaphel", v: "ishtaphel",
    w: "hithaphel", o: "polel", z: "ithpoel", r: "hithpolel", f: "hithpalpel", b: "hephal", c: "tiphel",
    m: "poel", l: "palpel", L: "ithpalpel", O: "ithpolel", G: "ittaphal",
  };
  const FORMS = {
    p: "qatal (перфект)", q: "weqatal (перфект с союзом)", i: "yiqtol (имперфект)",
    w: "wayyiqtol (повествовательная форма)", h: "когортатив (побуждение от 1-го лица)",
    j: "юссив (пожелание, повеление 3-му лицу)", v: "повелительная форма",
    r: "причастие действительное", s: "причастие страдательное",
    a: "инфинитив абсолютный", c: "инфинитив конструктный",
  };
  const GENDER = { m: "м. р.", f: "ж. р.", b: "м. или ж. р.", c: "общий род" };
  const NUMBER = { s: "ед. ч.", p: "мн. ч.", d: "двойств. ч." };
  const STATE = { a: "", c: "сопряжённое состояние", d: "определённое" };
  const PERSON = { 1: "1 л.", 2: "2 л.", 3: "3 л." };
  const NOUN = { c: "существительное", g: "название народа", p: "имя собственное" };
  const ADJ = { a: "прилагательное", c: "числительное", g: "название народа (прил.)", o: "порядковое числительное" };
  const PRON = { d: "указательное местоимение", f: "неопределённое местоимение", i: "вопросительное местоимение",
    p: "личное местоимение", r: "относительное местоимение" };
  const SUFFIX = { d: "окончание направления («-ah»)", h: "добавочное «-ah»", n: "добавочное «-n»",
    p: "местоименное окончание" };
  const PARTICLE = { a: "частица утверждения", d: "определённый артикль", e: "частица побуждения",
    i: "вопросительная частица", j: "междометие", m: "указательная частица", n: "отрицание",
    o: "метка прямого дополнения", r: "относительная частица" };

  function pgn(s) {
    return [PERSON[s[0]], GENDER[s[1]], NUMBER[s[2]]].filter(Boolean).join(" ");
  }
  function gns(s) {
    return [GENDER[s[0]], NUMBER[s[1]], STATE[s[2]]].filter(Boolean).join(", ");
  }

  function segment(code, lang) {
    if (!code) return "";
    const pos = code[0], rest = code.slice(1);
    switch (pos) {
      case "V": {
        const stems = lang === "A" ? STEMS_A : STEMS_H;
        const stem = stems[rest[0]] || rest[0];
        const form = FORMS[rest[1]] || rest[1];
        const tail = rest.slice(2);
        const extra = "rs".includes(rest[1]) ? gns(tail) : pgn(tail);
        return ["глагол", "основа " + stem, form, extra].filter(Boolean).join(", ");
      }
      case "N": return [NOUN[rest[0]] || "существительное", gns(rest.slice(1))].filter(Boolean).join(", ");
      case "A": return [ADJ[rest[0]] || "прилагательное", gns(rest.slice(1))].filter(Boolean).join(", ");
      case "P": return [PRON[rest[0]] || "местоимение", pgn(rest.slice(1))].filter(Boolean).join(", ");
      case "S": return [SUFFIX[rest[0]] || "окончание", rest[0] === "p" ? pgn(rest.slice(1)) : ""].filter(Boolean).join(", ");
      case "T": return PARTICLE[rest[0]] || "частица";
      case "R": return rest === "d" ? "предлог с артиклем" : "предлог";
      case "C": return "союз";
      case "D": return "наречие";
      default: return code;
    }
  }
  return { segment };
})();
