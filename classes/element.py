import logging
import re
import sys
import decimal as dec

try:
    import datarow
except ImportError as exc:
    sys.stderr.write("Error: failed to import module ({})".format(exc))
    sys.exit(1)

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)-5s - %(message)s",
                    level=logging.DEBUG,
                    datefmt='%Y-%m-%d %H:%M:%S')
logger = logging.getLogger(__name__)


old_pattern_dance_notation = re.compile(r"^(?i)([1-4]S[1-4])([B1-4])*(\**)$")
indiv_scored_elts = re.compile(r"^(?i)([A-Z]{2,})L([B1-4])\+[A-Z]{2,}M([B1-4])$")
combo_nonjump_elts = re.compile(r"^(?i)([A-Z]{2,})([B1-4])(\**)\+([A-Z]{2,})([B1-4])(\**)$")
pattern_dance = re.compile(r"^(1[A-Z]{2}|2[A-Z]{2})([B1-4])\+kp([YTN]{3,4})(\**)$")
other_leveled_elts = re.compile(r"^(?i)([a-z]+(?<!Sp))([B1-4]{0,1})(\**)$")
throw_jumps = re.compile(r"^([1-4](Eu|T|S|Lo|F|Lz|A|LZ|LO)Th)([!e<*]{0,3})$")
jumps = re.compile(r"^([1-4](Eu|T(?!w)|S|Lo|F|Lz|A|LZ|LO)(?!Th))([!e<*]{0,3})\+*(COMBO|SEQ|REP)*")
spins = re.compile(r"^([A-Za-z]*Sp)(([B1-4])p)*([1-4])*(V([1-5])|V)*(\**)$")
pairs_elts = re.compile(r"^([1-5][A-Za-z]{2,3}(?<!Th|Eu|Lz|LZ|LO|Lo)(?<![TSFA]))([B1-4])*(\**)$")


ELT_TYPES = {"IceDance": {"Tw": "twizzles", "St": "steps", "Li": "lift", "Sp": "spin", "RH": "pattern dance",
                          "FS": "pattern dance", "ChSl": "slide", "1S": "pattern_dance", "2S": "pattern dance",
                          "PiF": "pivot"},
             "Pairs": {"Tw": "throw twist", "Th": "throw jump", "Li": "lift", "Sp": "spin", "Ds": "death spiral",
                       "St": "steps"},
             "Singles": {"St": "steps", "SpSq": "spiral", "ChSq": "choreo", "ChSp": "spiral", r"Sp": "spin"}
             }


def _parse_jumps(match_list, dic):
    sorted_tuples = [list(t) for t in zip(*match_list)]
    dic["elt_name"] = "+".join(sorted_tuples[0])
    dic["jump_list"] = sorted_tuples[0]
    dic["call_dic"] = {k + 1: v[2] if v[2] != "" else None for (k, v) in dict(enumerate(match_list)).items()}
    logger.debug(f"Call dic is {dic['call_dic']}")
    for jump in dic["call_dic"]:
        if dic["call_dic"][jump] is not None and "*" in dic["call_dic"][jump]:
            dic["invalid_flag"] = 1
            dic["call_dic"][jump] = dic["call_dic"][jump].replace("*", "")

    flag_list = [f for f in sorted_tuples[3] if f != ""]
    dic["combo_flag"] = 1 if "+" in dic["elt_name"] or "COMBO" in flag_list else 0
    dic["rep_flag"] = 1 if "REP" in flag_list else 0
    dic["seq_flag"] = 1 if "SEQ" in flag_list else 0
    return dic


def _parse_old_pattern_dances(match_list, dic):
    logger.debug(f"Match list is {match_list}")
    dic["elt_name"] = match_list[0][0]
    dic["elt_level"] = match_list[0][1]
    dic["invalid_flag"] = 1 if match_list[0][2] == "*" else 0
    return dic


def _parse_pattern_dance(match_list, dic):
    dic["elt_name"] = match_list[0][0]
    dic["elt_level"] = match_list[0][1]
    dic["elt_kps"] = match_list[0][2].split()
    dic["invalid_flag"] = 1 if match_list[0][3] == "*" else 0


def _parse_spins(match_list, dic):
    dic["elt_name"] = match_list[0][0]
    dic["no_positions"] = match_list[0][2]
    dic["elt_level"] = match_list[0][3]
    dic["failed_spin_flag"] = 1 if match_list[0][4] != "" else 0
    dic["missed_reqs"] = int(match_list[0][5]) if match_list[0][5] != "" else None
    dic["invalid_flag"] = 1 if match_list[0][6] == "*" else 0
    return dic


def _parse_indiv_scored_elts(match_list, dic):
    dic["elt_name"] = match_list[0][0]
    dic["elt_level_lady"] = match_list[0][1]
    dic["elt_level_man"] = match_list[0][2]
    # Add handling for invalidation, but not sure what those look like for these elements yet
    # invalid_flag_lady =
    # invalid_flag_man =
    # invalid_flag = 1 if invalid_flag_lady == 1 or invalid_flag_man == 1 else 0
    return dic


def _parse_combo_nonjump_elts(match_list, dic):
    dic["elt_1_name"] = match_list[0][0]
    dic["elt_1_level"] = match_list[0][1]
    dic["elt_1_invalid"] = 1 if match_list[0][2] == "*" else 0
    dic["elt_2_name"] = match_list[0][3]
    dic["elt_2_level"] = match_list[0][4]
    dic["elt_2_invalid"] = 1 if match_list[0][5] == "*" else 0
    dic["elt_name"] = dic["elt_1_name"] + "+" + dic["elt_2_name"]
    dic["invalid_flag"] = 1 if dic["elt_1_invalid"] == 1 or dic["elt_2_invalid"] == 1 else 0
    return dic


def _parse_throw_jumps(match_list, dic):
    dic["elt_name"] = match_list[0][0]
    dic["call_dic"] = {1: match_list[0][2] if match_list[0][2] != "" else None}
    if dic["call_dic"][1] is not None and "*" in dic["call_dic"][1]:
        dic["invalid_flag"] = 1
        dic["call_dic"][1] = dic["call_dic"][1].replace("*", "")
    return dic


def _parse_other_leveled_elts(match_list, dic):
    dic["elt_name"] = match_list[0][0]
    dic["elt_level"] = match_list[0][1] if match_list[0][1] != "" else None
    dic["invalid_flag"] = 1 if match_list[0][2] == "*" else 0
    return dic


def _parse_pairs_elts(match_list, dic):
    dic["elt_name"] = match_list[0][0]
    dic["elt_level"] = match_list[0][1] if match_list[0][1] != "" else None
    dic["invalid_flag"] = 1 if match_list[0][2] == "*" else 0
    return dic


def _parse_elt_scores(elt_row, judges):
    cutoff = -1 - judges
    factored_totals = datarow.DataRow(raw_list=elt_row[2:cutoff]).clean_scores_row(mode="decimal")
    bv, sov_goe = dec.Decimal(factored_totals[0]), dec.Decimal(factored_totals[1])
    goe = datarow.DataRow(raw_list=elt_row[cutoff:-1]).clean_scores_row(mode="int")
    total = dec.Decimal(str(elt_row[-1]))
    return bv, goe, sov_goe, total


EXPECTED_PATTERNS = {"IceDance": [indiv_scored_elts, combo_nonjump_elts, spins, pattern_dance, other_leveled_elts,
                                  old_pattern_dance_notation],
                     "Singles": [jumps, spins, other_leveled_elts],
                     "Pairs": [throw_jumps, jumps, spins, pairs_elts, other_leveled_elts]
                     }

PATTERN_PARSERS = {jumps: _parse_jumps,
                   indiv_scored_elts: _parse_indiv_scored_elts,
                   combo_nonjump_elts: _parse_combo_nonjump_elts,
                   pattern_dance: _parse_pattern_dance,
                   other_leveled_elts: _parse_other_leveled_elts,
                   old_pattern_dance_notation: _parse_old_pattern_dances,
                   spins: _parse_spins,
                   throw_jumps: _parse_throw_jumps,
                   pairs_elts: _parse_pairs_elts
                   }


def parse_elt_name(text, meta_disc, parsed_dic):
    keys = PATTERN_PARSERS.keys() & set(EXPECTED_PATTERNS[meta_disc])
    parser_subset = {k: PATTERN_PARSERS[k] for k in keys}

    # Check only one match
    searches = [re.findall(p, text) for p in EXPECTED_PATTERNS[meta_disc]]
    filtered_searches = [s for s in searches if s != []]
    if not filtered_searches:
        raise ValueError(f"Could not find elt matching expected patterns in {text}")
    elif len(filtered_searches) > 1:
        raise ValueError(f"Found multiple parsing possibilities for {text}: {searches}")

    # Use parser specific to each detected pattern
    for pattern in parser_subset:
        if re.findall(pattern, text):
            return parser_subset[pattern](match_list=re.findall(pattern, text), dic=parsed_dic)


class Element:
    def __init__(self, meta_disc, no, name, bv, goe, sov_goe, total, invalid_flag):
        if sum([bv, sov_goe]).compare(total) != dec.Decimal("0"):
            raise ValueError(f"Instantiation of element {name} failed as bv ({bv}) and goe ({sov_goe}) did not sum to "
                             f"total ({total})")
        self.meta_discipline = meta_disc
        self.name = name
        self.no = no
        self.type = self._classify_elt()
        self.bv = dec.Decimal(bv)
        self.goe = goe
        self.sov_goe = dec.Decimal(sov_goe)
        self.total = dec.Decimal(total)
        self.invalid_flag = invalid_flag
        logger.debug(f"Instantiated Element object: {self.no}, {self.name} ({self.type}), {self.bv} + {self.sov_goe} "
                     f"= {self.total}, {'invalid' if self.invalid_flag == 1 else 'valid'}")

    def _classify_elt(self):
        for key in ELT_TYPES[self.meta_discipline]:
            if key in self.name:
                return ELT_TYPES[self.meta_discipline][key]
        if re.search(jumps, self.name):
            return "jump"
        logger.error(f"Could not find element type for {self.name}")
        sys.exit(f"Could not find element type for {self.name}")


class IceDanceElement(Element):
    def __init__(self, elt_row, judges):
        logger.debug(f"raw elt row is {elt_row}")
        parsed_dic = {"elt_name": None, "elt_1_name": None, "elt_2_name": None,
                      "elt_level": None, "elt_level_lady": None, "elt_level_man": None,
                      "elt_1_level": None, "elt_2_level": None, "elt_kps": None,
                      "elt_1_invalid": 0, "elt_2_invalid": 0, "invalid_flag": 0}

        parsed_dic = parse_elt_name(text=elt_row[1], meta_disc="IceDance", parsed_dic=parsed_dic)
        bv, goe, sov_goe, total = _parse_elt_scores(elt_row, judges)

        super().__init__(meta_disc="IceDance", no=elt_row[0], name=parsed_dic["elt_name"], bv=bv, goe=goe,
                         sov_goe=sov_goe, total=total,
                         invalid_flag=parsed_dic["invalid_flag"])

        self.elt_1_name, self.elt_2_name = parsed_dic["elt_1_name"], parsed_dic["elt_2_name"]
        self.elt_level = parsed_dic["elt_level"]
        self.elt_level_lady, self.elt_level_man = parsed_dic["elt_level_lady"], parsed_dic["elt_level_man"]
        self.elt_1_level, self.elt_2_level = parsed_dic["elt_1_level"], parsed_dic["elt_2_level"]
        self.elt_kps = parsed_dic["elt_kps"]


class SinglesElement(Element):
    def __init__(self, elt_row, judges):
        logger.debug(f"raw elt row is {elt_row}")
        parsed_dic = {"elt_name": None, "jump_list": None, "call_dic": None,
                      "elt_level": None, "no_positions": None, "failed_spin_flag": None,
                      "missed_reqs": None, "combo_flag": None, "seq_flag": None, "rep_flag": None,
                      "invalid_flag": 0}

        parsed_dic = parse_elt_name(text=elt_row[1], meta_disc="Singles", parsed_dic=parsed_dic)
        bv, goe, sov_goe, total = _parse_elt_scores(elt_row, judges)

        super().__init__(meta_disc="Singles", no=elt_row[0], name=parsed_dic["elt_name"], bv=bv, goe=goe,
                         sov_goe=sov_goe, total=total,
                         invalid_flag=parsed_dic["invalid_flag"])

        self.jump_list, self.call_dic = parsed_dic["jump_list"], parsed_dic["call_dic"]
        self.elt_level = parsed_dic["elt_level"]
        self.no_positions, self.failed_spin_flag = parsed_dic["no_positions"], parsed_dic["failed_spin_flag"]
        self.missed_reqs, self.combo_flag = parsed_dic["missed_reqs"], parsed_dic["combo_flag"]
        self.seq_flag, self.rep_flag = parsed_dic["seq_flag"], parsed_dic["rep_flag"]


class PairsElement(Element):
    def __init__(self, elt_row, judges):
        logger.debug(f"raw elt row is {elt_row}")
        parsed_dic = {"elt_name": None, "jump_list": None, "call_dic": None,
                      "elt_level": None, "no_positions": None, "failed_spin_flag": None,
                      "missed_reqs": None, "combo_flag": None, "seq_flag": None, "rep_flag": None,
                      "invalid_flag": 0}
        parsed_dic = parse_elt_name(text=elt_row[1], meta_disc="Pairs", parsed_dic=parsed_dic)
        bv, goe, sov_goe, total = _parse_elt_scores(elt_row, judges)

        super().__init__(meta_disc="Pairs", no=elt_row[0], name=parsed_dic["elt_name"], bv=bv, goe=goe,
                         sov_goe=sov_goe, total=total, invalid_flag=parsed_dic["invalid_flag"])

        self.jump_list, self.call_dic = parsed_dic["jump_list"], parsed_dic["call_dic"]
        self.elt_level = parsed_dic["elt_level"]
        self.no_positions, self.failed_spin_flag = parsed_dic["no_positions"], parsed_dic["failed_spin_flag"]
        self.missed_reqs, self.combo_flag = parsed_dic["missed_reqs"], parsed_dic["combo_flag"]
        self.seq_flag, self.rep_flag = parsed_dic["seq_flag"], parsed_dic["rep_flag"]
