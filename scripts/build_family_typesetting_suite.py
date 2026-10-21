#!/usr/bin/env python3
"""Build a family-owned proof suite through the shared semantic document template.

The style and copy manifest are supplied by the caller. This module contains no
brand tokens, font files, identity artwork, or family-specific source content.
PDFs use the existing Tectonic/Poppler toolchain; web output is static HTML/CSS.
"""
from __future__ import annotations

import argparse
import hashlib
from html.parser import HTMLParser
import json
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from sheepfling_styling.typography_roles import (
    SHARED_TYPE_ROLES, PHYSICAL_TYPE_ROLES, tex_role_definitions, validate_role_map,
)

BAD_TEX = re.compile(r"Overfull \\[hv]box|Missing character|Font Warning|Emergency stop|Citation .* undefined", re.I)
OUTPUTS = ("one-page", "two-page", "product-slick", "component-proof")


class BuildError(ValueError):
    pass


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run(command: list[str], cwd: Path) -> str:
    try:
        result = subprocess.run(command, cwd=cwd, check=True, text=True,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        return result.stdout
    except (OSError, subprocess.CalledProcessError) as exc:
        output = getattr(exc, "stdout", "") or ""
        raise BuildError("Command failed: {}\n{}".format(" ".join(command), output[-6000:])) from exc


def read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BuildError("Cannot read manifest: {}".format(path)) from exc
    if not isinstance(data, dict):
        raise BuildError("Manifest root must be an object: {}".format(path))
    return data


def tex(value: str) -> str:
    replacements = {
        "\\": r"\textbackslash{}", "{": r"\{", "}": r"\}", "$": r"\$",
        "&": r"\&", "#": r"\#", "%": r"\%", "_": r"\_",
        "~": r"\textasciitilde{}", "^": r"\textasciicircum{}",
    }
    return "".join(replacements.get(ch, ch) for ch in value)


def validate_manifest(style: dict[str, Any], content: dict[str, Any]) -> None:
    for key in ("family_id", "display_name", "profile_version", "status", "output_dir", "type", "colors", "accents", "sources"):
        if key not in style:
            raise BuildError("Style manifest is missing {}".format(key))
    if style["profile_version"] != "0.1.0":
        raise BuildError("This proof run is pinned to profile version 0.1.0")
    for key in ("title", "subtitle", "lead", "sections", "table", "figure", "cards", "references", "appendix", "footnote", "one_page", "product_slick"):
        if key not in content:
            raise BuildError("Content manifest is missing {}".format(key))
    if len(content["sections"]) < 3:
        raise BuildError("The common proof requires three narrative sections")
    if len(content["table"]["rows"]) < 4:
        raise BuildError("The common proof table needs at least four wrapping rows")
    if len(content["cards"]) != 4:
        raise BuildError("The common proof requires note, caution, specification, and example cards")
    expected = {"NOTE", "CAUTION", "SPECIFICATION", "EXAMPLE"}
    if {card.get("kind") for card in content["cards"]} != expected:
        raise BuildError("Informative card variants must be labeled NOTE, CAUTION, SPECIFICATION, and EXAMPLE")
    if not str(content["one_page"].get("summary", "")).strip():
        raise BuildError("The one_page block needs a family-specific summary")
    if "one_page_composition" in style:
        composition = style["one_page_composition"]
        required_slots = {"navigation", "title", "subtitle", "lead", "status_chips", "panels", "actions", "source_note"}
        flow = composition.get("flow") if isinstance(composition, dict) else None
        if not isinstance(flow, list) or set(flow) != required_slots or len(flow) != len(required_slots):
            raise BuildError("one_page_composition.flow must order each supported one-page slot exactly once")
        if composition.get("panel_layout", "paired") not in {"paired", "stacked"}:
            raise BuildError("one_page_composition.panel_layout must be paired or stacked")
        ui = content.get("ui_components")
        if not isinstance(ui, dict):
            raise BuildError("A composed one-page layout needs ui_components content")
        tabs, chips, panels, actions = (ui.get(key) for key in ("tabs", "status_chips", "panels", "actions"))
        if not isinstance(tabs, list) or len(tabs) < 2 or sum(item.get("state") == "selected" for item in tabs if isinstance(item, dict)) != 1:
            raise BuildError("ui_components.tabs needs at least two tabs and exactly one selected state")
        if any(not isinstance(item, dict) or not str(item.get("label", "")).strip() for item in tabs):
            raise BuildError("Every UI tab needs a non-empty label")
        if not isinstance(chips, list) or not chips:
            raise BuildError("ui_components.status_chips needs at least one status chip")
        if any(not isinstance(item, dict) or not str(item.get("label", "")).strip() for item in chips):
            raise BuildError("Every UI status chip needs a non-empty label")
        if not isinstance(panels, list) or len(panels) < 2:
            raise BuildError("ui_components.panels needs at least two informational panels")
        if composition.get("panel_layout", "paired") == "paired" and len(panels) != 2:
            raise BuildError("A paired panel layout needs exactly two informational panels")
        if any(not isinstance(item, dict) or item.get("state") not in {"selected", "unselected"} for item in tabs):
            raise BuildError("Every UI tab needs an explicit selected or unselected state")
        if any(not isinstance(item, dict) or item.get("tone", "quiet") not in {"quiet", "emphasis"} for item in panels):
            raise BuildError("UI panel tone must be quiet or emphasis")
        if any(not isinstance(item, dict) or any(not str(item.get(key, "")).strip() for key in ("label", "title", "body")) for item in panels):
            raise BuildError("Every UI panel needs a non-empty label, title and body")
        if not isinstance(actions, list) or len(actions) != 2 or {item.get("kind") for item in actions if isinstance(item, dict)} != {"primary", "secondary"}:
            raise BuildError("ui_components.actions needs one primary and one secondary action")
        if any(not isinstance(item, dict) or not str(item.get("label", "")).strip() for item in actions):
            raise BuildError("Every UI action needs a non-empty label")
        if any(not isinstance(item, dict) or item.get("direction", "none") not in {"back", "forward", "none"} for item in actions):
            raise BuildError("UI action direction must be back, forward, or none")
    product = content["product_slick"]
    for key in ("eyebrow", "title", "subtitle", "description", "highlights", "facts", "next_step", "source_note"):
        if key not in product:
            raise BuildError("The product_slick block is missing {}".format(key))
    if len(product["highlights"]) < 2 or len(product["facts"]) < 2:
        raise BuildError("The product_slick block needs at least two highlights and two source-backed facts")
    if not {"body", "display", "strong"}.issubset(style["type"]):
        raise BuildError("Type manifest must define body, display, and strong roles")
    role_map = style.get("role_map")
    try:
        validate_role_map(role_map, style["type"])
    except ValueError as exc:
        raise BuildError(str(exc)) from exc
    for source in style["sources"]:
        path = Path(source["path"])
        if not path.is_file():
            raise BuildError("Missing declared source file: {}".format(path))
        if source.get("sha256") and sha256(path) != source["sha256"]:
            raise BuildError("Source hash differs from the manifest: {}".format(path))
    for face in style["type"].values():
        if face.get("path") and not Path(face["path"]).is_file():
            raise BuildError("Missing declared font file: {}".format(face["path"]))
        if face.get("path") and face.get("sha256") and sha256(Path(face["path"])) != face["sha256"]:
            raise BuildError("Font source hash differs from the manifest: {}".format(face["path"]))


def color(name: str, value: str) -> str:
    if not re.fullmatch(r"#[0-9A-Fa-f]{6}", value):
        raise BuildError("{} must be a six-digit RGB value".format(name))
    return value[1:].upper()


def font_command(role: str, face: dict[str, Any], faces: dict[str, Any] | None = None) -> str:
    font_path = Path(face.get("build_path") or face["path"]).resolve()
    font_name = tex(face.get("filename") or font_path.name)
    directory = "fonts/"
    if role == "body":
        bold = ""
        if faces and "strong" in faces:
            bold = ",BoldFont={" + tex(faces["strong"].get("filename") or Path(faces["strong"].get("build_path") or faces["strong"]["path"]).name) + "}"
        return "\\setmainfont{" + font_name + "}[Path={" + directory + "}" + bold + "]\n\\newcommand{\\BodyFace}{\\rmfamily}\n"
    command = {"display": "DisplayFace", "strong": "StrongFace", "wordmark": "WordmarkFace", "mono": "MonoFace"}[role]
    return "\\newfontfamily\\" + command + "{" + font_name + "}[Path={" + directory + "}]\n"


def tex_preamble(style: dict[str, Any], mode: str, work: Path) -> str:
    c = style.get("print_colors", style["colors"])
    fonts = style["type"]
    inner = style.get("geometry", {}).get("inner_mm", 20)
    outer = style.get("geometry", {}).get("outer_mm", 18)
    top = style.get("geometry", {}).get("top_mm", 18)
    bottom = style.get("geometry", {}).get("bottom_mm", 18)
    paper = style.get("geometry", {}).get("paper", "letterpaper")
    if paper not in {"a4paper", "letterpaper"}:
        raise BuildError("geometry.paper must be a4paper or letterpaper")
    sizes = {"one-page": "9.5pt", "two-page": "10pt", "product-slick": "10pt", "component-proof": "10.5pt"}
    family_title = tex(style["display_name"])
    rules = style["accents"]
    acc = tex(rules.get("marker", "01"))
    markers = {
        "square-index": r"\tikz[baseline=-.55ex]{\node[draw=Accent,fill=Page,line width=.7pt,inner sep=2.2pt,minimum width=12pt,minimum height=11pt,rectangle]{" + acc + r"};}",
        "dotted-rail": r"\tikz[baseline=-.55ex]{\fill[Accent] (0,0) circle (1.1pt);\draw[Accent,densely dotted,line width=.65pt] (2pt,0)--(17pt,0);\draw[Accent,line width=.65pt] (21pt,1.8pt) rectangle (24.6pt,-1.8pt);}",
        "dot-chip-rail": r"\tikz[baseline=-.55ex]{\fill[Accent] (0,0) circle (1.2pt);\draw[Accent,densely dotted,line width=.65pt] (2pt,0)--(17pt,0);\fill[Line] (20pt,0) circle (.9pt);\fill[Line] (25pt,0) circle (.9pt);}",
        "bookmark-rule": r"\tikz[baseline=-.55ex]{\draw[Accent,line width=.45pt] (0,0)--(26pt,0);\fill[Secondary] (2pt,0) circle (1pt);}",
        "offset-panel": r"\tikz[baseline=-.55ex]{\fill[Accent] (0,-2pt)--(24pt,-2pt)--(27pt,1pt)--(3pt,1pt)--cycle;\draw[Ink,line width=.65pt] (1pt,2pt)--(25pt,2pt);}",
        "organic-cells": r"\tikz[baseline=-.55ex,x=1pt,y=1pt]{\foreach \x/\y in {0/0,5/0,2.5/4.3,7.5/4.3}{\draw[Accent,line width=.45pt] (\x,\y) -- ++(2.5pt,1.45pt) -- ++(0pt,2.9pt) -- ++(-2.5pt,1.45pt) -- ++(-2.5pt,-1.45pt) -- ++(0pt,-2.9pt) -- cycle;}}",
        "amber-band": r"\tikz[baseline=-.55ex]{\fill[Accent] (0,-3pt) rectangle (4pt,4pt);\draw[Line,line width=.55pt] (7pt,0)--(27pt,0);}",
    }
    marker_type = rules.get("marker_type", "square-index")
    if marker_type not in markers:
        raise BuildError("Unknown semantic marker type: {}".format(marker_type))
    accent_style = markers[marker_type]
    tag_shape = rules.get("tag_shape", "square")
    tag_corners = "rounded corners=3pt" if tag_shape == "rounded" else "sharp corners"
    card_shape = rules.get("card_shape", "square")
    card_corners = "arc=2mm" if card_shape in {"rounded", "offset"} else "sharp corners"
    card_border = "leftrule=2pt,rightrule=0pt,toprule=0pt,bottomrule=0pt" if card_shape == "offset" else ""
    def stage_asset(key: str) -> Path | None:
        asset = style.get(key)
        if not asset:
            return None
        source = Path(asset)
        if not source.is_absolute():
            source = work / source
        if not source.is_file():
            return None
        local = work / "assets" / source.name
        local.parent.mkdir(parents=True, exist_ok=True)
        if source.resolve() != local.resolve():
            shutil.copy2(source, local)
        return local

    img_source = stage_asset("print_identity_asset") or stage_asset("identity_asset")
    if img_source and img_source.suffix.lower() == ".svg":
        local_pdf = img_source.with_suffix(".pdf")
        run([shutil.which("rsvg-convert") or "rsvg-convert", "-f", "pdf", "-o", str(local_pdf), str(img_source)], work)
        img_tex = r"\includegraphics[height=14mm]{assets/" + tex(local_pdf.name) + "}"
    elif img_source:
        img_tex = r"\includegraphics[height=14mm,keepaspectratio]{assets/" + tex(img_source.name) + "}"
    else:
        img_tex = r"\hspace{0pt}"
    accent_source = stage_asset("accent_asset")
    if accent_source and accent_source.suffix.lower() == ".svg":
        accent_pdf = accent_source.with_suffix(".pdf")
        run([shutil.which("rsvg-convert") or "rsvg-convert", "-f", "pdf", "-o", str(accent_pdf), str(accent_source)], work)
        accent_tex = r"\includegraphics[height=10mm,width=22mm,keepaspectratio]{assets/" + tex(accent_pdf.name) + "}"
    elif accent_source:
        accent_tex = r"\includegraphics[height=10mm,width=22mm,keepaspectratio]{assets/" + tex(accent_source.name) + "}"
    else:
        accent_tex = ""
    template = r"""\documentclass[__SIZE__,twoside]{article}
\usepackage[__PAPER__,inner=__INNER__mm,outer=__OUTER__mm,top=__TOP__mm,bottom=__BOTTOM__mm,headheight=12pt,headsep=8pt,footskip=18pt]{geometry}
\usepackage{fontspec,xcolor,graphicx,tikz,tcolorbox,booktabs,longtable,array,ragged2e,fancyhdr,hyperref,enumitem,caption,colortbl}
\defaultfontfeatures{Ligatures=TeX,Kerning=On}
__FONTS__
\definecolor{Page}{HTML}{__PAGE__}\definecolor{Card}{HTML}{__CARD__}\definecolor{Ink}{HTML}{__INK__}\definecolor{Muted}{HTML}{__MUTED__}
\definecolor{Accent}{HTML}{__ACCENT__}\definecolor{Secondary}{HTML}{__SECONDARY__}\definecolor{Line}{HTML}{__LINE__}\definecolor{Tint}{HTML}{__TINT__}
\pagecolor{Page}\color{Ink}
\hypersetup{unicode=true,colorlinks=true,linkcolor=Accent,urlcolor=Accent,pdftitle={__PDFTITLE__},pdfsubject={__SUBJECT__}}
\setlength\parindent{0pt}\setlength{\parskip}{4pt}\setlength\emergencystretch{1.25em}\hyphenpenalty=3000\exhyphenpenalty=3000\tolerance=2000
\DeclareCaptionFont{semantic}{\TypeCaption}\captionsetup{font={semantic,small},labelfont=bf,skip=4pt}
\newcommand{\AccentMark}{__ACCENTMARK__}
\newcommand{\AccentArtwork}{__ACCENTARTWORK__}
\newcommand{\BrandLockup}{\raisebox{-1.5mm}{__IMAGE__}\hspace{3mm}{__WORDMARK__\color{Accent} __BRAND__}}
\newcommand{\BrandTag}{\tikz[baseline=-.45ex]\node[draw=Line,fill=Tint,line width=.55pt,__TAGSHAPE__,inner xsep=4pt,inner ysep=2pt]{\TypeDocumentEyebrow\small __STATUS__};}
\newcommand{\SectionHead}[2]{\refstepcounter{section}\addcontentsline{toc}{section}{\protect\numberline{\thesection}#2}\markboth{#2}{}\par\vspace{.8em}\noindent\AccentMark\hspace{.8em}{\TypeSectionHeading\color{Accent}\large #2}\hfill{\TypeSectionMarker\color{Muted}\scriptsize #1}\par\vspace{.3em}\color{Line}\rule{\linewidth}{.45pt}\color{Ink}\vspace{.2em}\par}
\newtcolorbox{NoteCard}[1][]{colback=Card,colframe=Line,boxrule=.55pt,__CARDSTYLE__,__CARDBORDER__,left=3mm,right=3mm,top=2.3mm,bottom=2.3mm,before skip=2.5mm,after skip=2.5mm,#1}
\newtcolorbox{TintCard}[1][]{colback=Tint,colframe=Accent,boxrule=.55pt,__CARDSTYLE__,__CARDBORDER__,left=3mm,right=3mm,top=2.3mm,bottom=2.3mm,before skip=2.5mm,after skip=2.5mm,#1}
\newcommand{\CardHeading}[2]{{\TypeLabel\color{Accent}\scriptsize\MakeUppercase{#1}\hfill\TypeCardTitle\color{Ink}\normalsize #2\par}\vspace{1mm}}
\newcommand{\RunningMatter}{\pagestyle{fancy}\fancyhf{}\renewcommand\headrulewidth{.35pt}\fancyhead[LE,RO]{\TypeLabel\color{Muted}\scriptsize __BRAND__ / \nouppercase{\leftmark}}\fancyhead[LO,RE]{\BrandTag}\fancyfoot[LE,RO]{\TypeFooter\color{Accent}\small\thepage}\fancyfoot[LO,RE]{\TypeFooter\color{Muted}\scriptsize LOCAL SPECIMEN / __CONTEXT__}}
\newcommand{\SrgbIntent}{__SRGB_SPECIALS__}
\begin{document}\SrgbIntent\TypeBody
"""
    substitutions = {
        "__SIZE__": sizes[mode], "__PAPER__": paper, "__INNER__": str(inner), "__OUTER__": str(outer), "__TOP__": str(top), "__BOTTOM__": str(bottom),
        "__FONTS__": "".join(font_command(k, v, fonts) for k, v in fonts.items()) + tex_role_definitions(style["role_map"], fonts),
        "__PAGE__": color("page", c["page"]), "__CARD__": color("card", c.get("card", c["page"])),
        "__INK__": color("ink", c["ink"]), "__MUTED__": color("muted", c["muted"]),
        "__ACCENT__": color("accent", c["accent"]), "__SECONDARY__": color("secondary", c.get("secondary", c["accent"])),
        "__LINE__": color("line", c.get("line", c["accent"])), "__TINT__": color("tint", c.get("tint", c["page"])),
        "__PDFTITLE__": tex(style["display_name"] + " typesetting proof"), "__SUBJECT__": tex(style.get("status", "local typesetting study")),
        "__SRGB_SPECIALS__": (r"\special{pdf:fstream @SpecimenSRGB (assets/sRGB.icc) << /N 3 >>}\special{pdf:put @catalog << /OutputIntents [ << /Type /OutputIntent /S /GTS_PDFA1 /OutputConditionIdentifier (sRGB IEC61966-2.1) /RegistryName (http://www.color.org) /Info (sRGB screen proof; not a print certification) /DestOutputProfile @SpecimenSRGB >> ] >>}" if style.get("require_srgb_output_intent") else ""),
        "__ACCENTMARK__": accent_style, "__ACCENTARTWORK__": accent_tex, "__IMAGE__": img_tex,
        "__WORDMARK__": r"\TypeIdentityWordmark",
        "__TAGSHAPE__": tag_corners, "__CARDSTYLE__": card_corners, "__CARDBORDER__": card_border,
        "__BRAND__": family_title, "__STATUS__": tex(style.get("status_label", "TYPOGRAPHY STUDY")),
        "__CONTEXT__": tex(style.get("context", "LIGHT")),
    }
    for key, value in substitutions.items():
        template = template.replace(key, value)
    template = template.replace(",,", ",")
    return template


def references_tex(content: dict[str, Any]) -> str:
    rows = []
    for i, item in enumerate(content["references"], 1):
        rows.append(r"\item[\textbf{" + str(i) + r".}] \textbf{" + tex(item["title"]) + r".} " + tex(item["detail"]) + "\n")
    return r"\begin{description}[leftmargin=1.1cm,style=nextline]" + "\n" + "".join(rows) + r"\end{description}"


def table_tex(content: dict[str, Any]) -> str:
    table = content["table"]
    headers = " & ".join(r"\TypeDataAxis\color{Accent}\small " + tex(x) for x in table["columns"])
    widths = table.get("column_widths", [0.18, 0.3, 0.42])
    if len(widths) != len(table["columns"]) or abs(sum(widths) - 1) > 0.02:
        raise BuildError("Table column widths must match columns and sum to 1")
    # p-columns include 2\tabcolsep each. Subtract their total internal padding
    # from the requested measure so a 100%-width table does not overflow.
    gap_adjust_pt = 12 * (len(widths) - 1) / len(widths)
    specs = " ".join(r">{\RaggedRight\arraybackslash}p{\dimexpr" + str(width) + r"\linewidth-" + str(gap_adjust_pt) + r"pt\relax}" for width in widths)
    lines = [r"\begin{longtable}{@{}" + specs + r"@{}}", r"\caption{" + tex(table["caption"]) + r"}\label{tab:shared-components}\\",
             r"\toprule " + headers + r"\\\midrule", r"\endfirsthead",
             r"\multicolumn{" + str(len(widths)) + r"}{@{}l}{\TypeBodyStrong\color{Muted}\small Table continued}\\\toprule " + headers + r"\\\midrule", r"\endhead",
             r"\midrule\multicolumn{" + str(len(widths)) + r"}{r@{}}{\TypeBodyStrong\color{Muted}\scriptsize Continued on next page}\\", r"\endfoot", r"\bottomrule", r"\endlastfoot"]
    for row in table["rows"]:
        if len(row) != len(widths):
            raise BuildError("Every table row must match the number of columns")
        lines.append(" & ".join(r"\TypeBody " + tex(str(cell)) for cell in row) + r"\\[3pt]")
    lines.append(r"\end{longtable}")
    return "\n".join(lines)


def figure_tex(content: dict[str, Any]) -> str:
    labels = content["figure"]["steps"]
    if len(labels) != 4:
        raise BuildError("The shared process figure requires four labeled stages")
    parts = [r"\begin{tikzpicture}[>=stealth, node distance=4mm, every node/.style={font=\TypeBody\small}]" + "\n"]
    for i, label in enumerate(labels):
        x = i * 3.15
        parts.append(r"\node[draw=Accent,fill=Tint,rounded corners=1mm,minimum width=27mm,minimum height=12mm,align=center] (p" + str(i) + r") at (" + str(x) + r",0) {\TypeBodyStrong\color{Accent}" + tex(label) + "};\n")
        if i:
            parts.append(r"\draw[->,color=Accent,line width=.7pt] (p" + str(i-1) + r".east) -- (p" + str(i) + ".west);\n")
    parts.append(r"\end{tikzpicture}")
    return "".join(parts)


def section_tex(item: dict[str, Any], index: int) -> str:
    paras = item["paragraphs"]
    if len(paras) < 1:
        raise BuildError("Every section needs at least one paragraph")
    output = [r"\SectionHead{" + str(index).zfill(2) + "}{" + tex(item["title"]) + "}"]
    if item.get("subheading"):
        output.append(r"\subsection*{" + tex(item["subheading"]) + "}\n")
    output.extend(tex(p) + "\\par\n" for p in paras)
    return "".join(output)


def cover(style: dict[str, Any], content: dict[str, Any], mode: str) -> str:
    title_size = {"one-page": "22", "two-page": "25", "product-slick": "28", "component-proof": "31"}[mode]
    lead_size = {"one-page": "10", "two-page": "12", "product-slick": "13", "component-proof": "13"}[mode]
    scope_card = "" if mode == "product-slick" else (r"\vspace{.7em}\begin{TintCard}\CardHeading{SCOPE}{" + tex(style.get("status_label", "SPECIMEN")) + r"}\TypeBody " + tex(style.get("note", "Typesetting review only.")) + r"\end{TintCard}")
    return (r"\thispagestyle{empty}\vspace*{.06\textheight}\noindent\BrandLockup\hfill\BrandTag\par\vspace{1.2em}" +
            r"\AccentMark\hfill\AccentArtwork\par\vspace{.7em}{\TypeDocumentTitle\color{Ink}\fontsize{" + title_size + r"}{" + str(int(title_size) + 5) + r"}\selectfont " + tex(content["title"]) + r"\par}" +
            r"\vspace{.55em}{\TypeDocumentSubtitle\color{Accent}\fontsize{" + lead_size + r"}{" + str(int(lead_size) + 4) + r"}\selectfont " + tex(content["subtitle"]) + r"\par}" +
            r"\vspace{.6em}{\TypeDocumentLead\color{Ink}\large " + tex(content["lead"]) + r"\par}" + scope_card)


def component_proof(style: dict[str, Any], content: dict[str, Any]) -> str:
    pieces = [cover(style, content, "component-proof"), r"\clearpage\RunningMatter\tableofcontents\clearpage"]
    for index, sec in enumerate(content["sections"], 1):
        pieces.append(section_tex(sec, index))
        if index == 1:
            pieces.extend([r"\begin{NoteCard}\CardHeading{NOTE}{" + tex(content["cards"][0]["title"]) + "}" + tex(content["cards"][0]["body"]) + r"\end{NoteCard}",
                           r"\begin{TintCard}\CardHeading{CAUTION}{" + tex(content["cards"][1]["title"]) + "}" + tex(content["cards"][1]["body"]) + r"\end{TintCard}"])
            pieces.append(r"A future reader should follow the sequence in Figure~\ref{fig:workflow}; the component choices are summarized in Table~\ref{tab:shared-components}.\footnote{" + tex(content["footnote"]) + "}")
        if index == 2:
            pieces.extend([table_tex(content), r"\begin{NoteCard}\CardHeading{SPECIFICATION}{" + tex(content["cards"][2]["title"]) + "}" + tex(content["cards"][2]["body"]) + r"\end{NoteCard}"])
        if index == 3:
            pieces.extend([r"\begin{figure}[htbp]\centering " + figure_tex(content) + r"\caption{" + tex(content["figure"]["caption"]) + r"}\label{fig:workflow}\end{figure}",
                           r"\begin{TintCard}\CardHeading{EXAMPLE}{" + tex(content["cards"][3]["title"]) + "}" + tex(content["cards"][3]["body"]) + r"\end{TintCard}"])
    pieces.append(r"\clearpage\section*{References}\addcontentsline{toc}{section}{References}" + references_tex(content))
    pieces.append(r"\clearpage\appendix\section{Component and source ledger}" +
                  r"\TypeBody " + tex(content["appendix"]["intro"]) + r"\begin{itemize}[leftmargin=1.2em]" +
                  "".join(r"\item " + tex(v) for v in content["appendix"]["items"]) + r"\end{itemize}" +
                  r"\begin{NoteCard}\CardHeading{PROVENANCE}{Source scope}" + tex(style.get("provenance_note", "The source files and layout assets are listed in the editable package.")) + r"\end{NoteCard}")
    return "\n".join(pieces) + "\n\\end{document}\n"


def compact_document(style: dict[str, Any], content: dict[str, Any], mode: str) -> str:
    pieces: list[str] = []
    compact_section = lambda item, index: section_tex({**item, "paragraphs": item["paragraphs"][:1]}, index)
    if mode == "two-page":
        pieces.extend([
            r"\vspace*{.006\textheight}\noindent\BrandTag\hfill{\TypeBodyStrong\color{Muted}\scriptsize " + tex(style["display_name"]) + r" / LIGHT SPECIMEN}\par\vspace{.25em}",
            r"\AccentMark\par\vspace{.15em}",
            r"{\TypeDocumentTitle\color{Ink}\fontsize{16}{19}\selectfont " + tex(content["title"]) + r"\par}",
            r"{\TypeBodyStrong\color{Accent}\fontsize{9}{11}\selectfont " + tex(content["subtitle"]) + r"\par}",
            r"{\TypeBody\footnotesize " + tex(content["lead"]) + r"\par}",
            r"\RunningMatter\vspace{.25em}",
        ])
        pieces.append(compact_section(content["sections"][0], 1))
        pieces.append(r"\begin{NoteCard}\CardHeading{NOTE}{" + tex(content["cards"][0]["title"]) + "}" + tex(content["cards"][0]["body"]) + r"\end{NoteCard}")
        facts = content["one_page"].get("facts", [])[:3]
        if facts:
            pieces.append(r"\begin{TintCard}\CardHeading{AT A GLANCE}{" + tex(style.get("status_label", "SPECIMEN")) + r"}\begin{itemize}[leftmargin=1.2em,itemsep=.05em]")
            pieces.extend(r"\item {\TypeBodyStrong " + tex(item["label"]) + r"}: " + tex(item["value"]) for item in facts)
            pieces.append(r"\end{itemize}\end{TintCard}")
        pieces.extend([r"\newpage\RunningMatter", compact_section(content["sections"][1], 2), compact_section(content["sections"][2], 3), table_tex(content),
                       r"\begin{figure}[ht]\centering " + figure_tex(content) + r"\caption{" + tex(content["figure"]["caption"]) + r"}\label{fig:workflow}\end{figure}",
                       r"\textbf{Source.} " + tex(content["references"][0]["detail"])])
    elif mode == "one-page":
        if style.get("one_page_composition"):
            return composed_one_page(style, content)
        one_page = content["one_page"]
        pieces = [r"\thispagestyle{empty}\vspace*{.025\textheight}\noindent\BrandLockup\hfill\BrandTag\par\vspace{.65em}",
                  r"\AccentMark\par\vspace{.3em}",
                  r"{\TypeDocumentTitle\color{Ink}\fontsize{24}{29}\selectfont " + tex(content["title"]) + r"\par}",
                  r"{\TypeBodyStrong\color{Accent}\fontsize{11}{14}\selectfont " + tex(content["subtitle"]) + r"\par}",
                  r"\vspace{.35em}{\TypeBody\large " + tex(content["lead"]) + r"\par}",
                  r"\SectionHead{01}{" + tex(one_page.get("heading", content["sections"][0]["title"])) + "}",
                  r"\TypeBody " + tex(one_page["summary"]) + r"\par\vspace{.25em}"]
        facts = content["one_page"].get("facts", [])
        if facts:
            pieces.append(r"\begin{NoteCard}\CardHeading{" + tex(one_page.get("facts_heading", "AT A GLANCE")) + "}{" + tex(style.get("status_label", "LOCAL SPECIMEN")) + r"}\begin{itemize}[leftmargin=1.2em,itemsep=.1em]")
            pieces.extend(r"\item {\TypeBodyStrong " + tex(item["label"]) + r"}: " + tex(item["value"]) for item in facts)
            pieces.append(r"\end{itemize}\end{NoteCard}")
        if one_page.get("closing"):
            pieces.append(r"\begin{TintCard}\CardHeading{" + tex(one_page.get("closing_label", "NEXT")) + "}{" + tex(one_page.get("closing_heading", "Before use")) + "}" + tex(one_page["closing"]) + r"\end{TintCard}")
        if one_page.get("source_note"):
            pieces.append(r"\vfill{\TypeBody\color{Muted}\footnotesize " + tex(one_page["source_note"]) + "}")
    elif mode == "product-slick":
        p = content["product_slick"]
        pieces = [r"\thispagestyle{empty}\vspace*{.02\textheight}\noindent\BrandLockup\hfill\BrandTag\par\vspace{.35em}",
                  r"\AccentMark\hfill\AccentArtwork\par\vspace{.15em}",
                  r"{\TypeBodyStrong\color{Accent}\small\MakeUppercase{" + tex(p["eyebrow"]) + r"}\par}",
                  r"{\TypeDocumentTitle\color{Ink}\fontsize{24}{28}\selectfont " + tex(p["title"]) + r"\par}",
                  r"{\TypeBodyStrong\color{Accent}\normalsize " + tex(p["subtitle"]) + r"\par}",
                  r"\vspace{.2em}{\TypeBody\small " + tex(p["description"]) + r"\par}",
                  r"\SectionHead{01}{" + tex(p.get("highlights_heading", "Highlights")) + "}",
                  r"\begin{itemize}[leftmargin=1.2em,itemsep=.05em,topsep=.1em]"]
        pieces.extend(r"\item[\AccentMark] \textbf{" + tex(item["label"]) + ".} " + tex(item["text"]) for item in p["highlights"])
        pieces.extend([r"\end{itemize}",
                       r"\begin{TintCard}\CardHeading{" + tex(p.get("facts_heading", "STATUS")) + "}{" + tex(style.get("status_label", "LOCAL SPECIMEN")) + r"}\begin{itemize}[leftmargin=1.2em,itemsep=.2em]"])
        pieces.extend(r"\item {\TypeBodyStrong " + tex(item["label"]) + r"}: " + tex(item["value"]) for item in p["facts"])
        pieces.extend([r"\end{itemize}\end{TintCard}",
                       r"\vspace{.15em}{\TypeBody\small\TypeBodyStrong Next: }{\TypeBody\small " + tex(p["next_step"]) + r"\par}",
                       r"{\TypeBody\color{Muted}\footnotesize " + tex(p["source_note"]) + "}"])
    return "\n".join(pieces) + "\n\\end{document}\n"


def _ui_tab_tex(item: dict[str, Any], style: dict[str, Any]) -> str:
    rounded = "arc=4mm" if style.get("accents", {}).get("tag_shape") == "rounded" else "sharp corners"
    if item["state"] == "selected":
        state = (r"\hspace{.25em}{\tikz[baseline=-.5ex]\draw[color=Page,line width=.7pt] "
                 r"(0,0)--(1.5pt,-1.5pt)--(4pt,1.8pt);\hspace{.4em}\TypeBody\scriptsize\color{Page}\textbf{SELECTED}}")
        fill, border, ink = "Accent", "Accent", "Page"
    else:
        state = ""
        fill, border, ink = "Card", "Line", "Accent"
    return (r"\tcbox[on line,boxsep=0pt,left=7pt,right=7pt,top=4pt,bottom=4pt," + rounded +
            r",colback=" + fill + r",colframe=" + border + r",boxrule=.6pt]{\TypeBodyStrong\small\color{" + ink + "}" +
            tex(item["label"]) + state + "}")


def ui_navigation_tex(style: dict[str, Any], content: dict[str, Any]) -> str:
    tabs = content["ui_components"]["tabs"]
    gap = float(style.get("one_page_composition", {}).get("tab_gap_mm", 2.5))
    if not 0 <= gap <= 12:
        raise BuildError("one_page_composition.tab_gap_mm must be between 0 and 12")
    separator = r"\hspace{" + str(gap) + r"mm}"
    return r"\noindent " + separator.join(_ui_tab_tex(item, style) for item in tabs) + r"\par"


def ui_status_chips_tex(style: dict[str, Any], content: dict[str, Any]) -> str:
    rounded = "arc=3mm" if style.get("accents", {}).get("tag_shape") == "rounded" else "sharp corners"
    chips = []
    for item in content["ui_components"]["status_chips"]:
        chips.append(r"\tcbox[on line,boxsep=0pt,left=6pt,right=6pt,top=3pt,bottom=3pt," + rounded +
                     r",colback=Tint,colframe=Line,boxrule=.5pt]{\TypeBodyStrong\scriptsize\color{Accent}" +
                     tex(item["label"]) + "}")
    gap = float(style.get("one_page_composition", {}).get("chip_gap_mm", 2.2))
    if not 0 <= gap <= 12:
        raise BuildError("one_page_composition.chip_gap_mm must be between 0 and 12")
    separator = r"\hspace{" + str(gap) + r"mm}"
    return r"\noindent " + separator.join(chips) + r"\par"


def ui_panel_tex(item: dict[str, Any], style: dict[str, Any]) -> str:
    fill = "Tint" if item.get("tone", "quiet") == "emphasis" else "Card"
    edge = "Accent" if item.get("tone", "quiet") == "emphasis" else "Line"
    rounded = "arc=2.4mm" if style.get("accents", {}).get("card_shape") == "rounded" else "sharp corners"
    return (r"\begin{tcolorbox}[" + rounded + r",colback=" + fill + r",colframe=" + edge +
            r",boxrule=.6pt,left=3mm,right=3mm,top=2.7mm,bottom=2.7mm,boxsep=0pt]" +
            r"{\TypeBodyStrong\color{Accent}\scriptsize\MakeUppercase{" + tex(item["label"]) + r"}}\\[.6mm]" +
            r"{\TypeDocumentTitle\color{Ink}\large " + tex(item["title"]) + r"\par}\vspace{.7mm}" +
            r"{\TypeBody\color{Ink}\small " + tex(item["body"]) + r"}" + r"\end{tcolorbox}")


def ui_panels_tex(style: dict[str, Any], content: dict[str, Any]) -> str:
    panels = content["ui_components"]["panels"]
    layout = style.get("one_page_composition", {}).get("panel_layout", "paired")
    if layout == "paired":
        return (r"\noindent\begin{minipage}[t]{.485\linewidth}" + ui_panel_tex(panels[0], style) +
                r"\end{minipage}\hfill\begin{minipage}[t]{.485\linewidth}" + ui_panel_tex(panels[1], style) +
                r"\end{minipage}\par")
    return "\n".join(ui_panel_tex(item, style) for item in panels) + r"\par"


def ui_actions_tex(style: dict[str, Any], content: dict[str, Any]) -> str:
    def render(item: dict[str, Any]) -> str:
        rounded = "arc=4mm" if style.get("accents", {}).get("tag_shape") == "rounded" else "sharp corners"
        fill, edge, ink = (("Accent", "Accent", "Page") if item["kind"] == "primary" else ("Card", "Line", "Accent"))
        direction = item.get("direction", "none")
        label = tex(item["label"])
        if direction == "back":
            label = r"$\leftarrow$\," + label
        elif direction == "forward":
            label += r"\,$\rightarrow$"
        return (r"\tcbox[on line,boxsep=0pt,left=9pt,right=9pt,top=5pt,bottom=5pt," + rounded +
                r",colback=" + fill + r",colframe=" + edge + r",boxrule=.7pt]{\TypeBodyStrong\normalsize\color{" +
                ink + "}" + label + "}")
    actions = content["ui_components"]["actions"]
    by_kind = {item["kind"]: render(item) for item in actions}
    return r"\noindent " + by_kind["secondary"] + r"\hfill " + by_kind["primary"] + r"\par"


def composed_one_page(style: dict[str, Any], content: dict[str, Any]) -> str:
    """Render semantic UI components in the family-owned one-page order."""
    composition = style["one_page_composition"]
    one_page = content["one_page"]
    spacing = composition.get("row_gap_mm", 4)
    title_gap = composition.get("title_gap_mm", 2)
    if not isinstance(spacing, (int, float)) or not 0 <= spacing <= 16:
        raise BuildError("one_page_composition.row_gap_mm must be between 0 and 16")
    if not isinstance(title_gap, (int, float)) or not 0 <= title_gap <= 12:
        raise BuildError("one_page_composition.title_gap_mm must be between 0 and 12")
    blocks = {
        "navigation": ui_navigation_tex(style, content),
        "title": r"{\TypeDocumentTitle\color{Ink}\fontsize{26}{31}\selectfont " + tex(content["title"]) + r"\par}",
        "subtitle": r"{\TypeBodyStrong\color{Accent}\fontsize{13}{17}\selectfont " + tex(content["subtitle"]) + r"\par}",
        "lead": r"{\TypeDocumentLead\color{Ink}\large " + tex(content["lead"]) + r"\par}",
        "status_chips": ui_status_chips_tex(style, content),
        "panels": ui_panels_tex(style, content),
        "actions": ui_actions_tex(style, content),
        "source_note": r"\vfill{\TypeBody\color{Muted}\footnotesize " + tex(one_page.get("source_note", "")) + "}",
    }
    pieces = [r"\thispagestyle{empty}\vspace*{.012\textheight}\noindent\BrandLockup\hfill\BrandTag\par"]
    for slot in composition["flow"]:
        gap = title_gap if slot in {"title", "subtitle"} else spacing
        pieces.append(r"\vspace{" + str(gap) + "mm}" + blocks[slot])
    return "\n".join(pieces) + "\n\\end{document}\n"


def product_slick_content_text(content: dict[str, Any]) -> str:
    """Return the family-owned title, offer copy, highlights, and facts."""
    product = content["product_slick"]
    parts = [product["title"], product["subtitle"], product["description"], product["next_step"], product["source_note"]]
    parts.extend(item["label"] + " " + item["text"] for item in product["highlights"])
    parts.extend(item["label"] + " " + item["value"] for item in product["facts"])
    return "\n".join(parts)


def html_document(style: dict[str, Any], content: dict[str, Any], out: Path, work: Path) -> dict[str, Any]:
    colors = style.get("web_colors", style["colors"])
    display = style["type"]["display"].get("family", "serif")
    body = style["type"]["body"].get("family", "serif")
    (out / "assets").mkdir(parents=True, exist_ok=True)
    web_assets = list(style.get("web_assets", []))
    for key in ("web_identity", "identity_asset", "accent_asset"):
        if style.get(key):
            candidate = Path(style[key])
            if not candidate.is_absolute():
                candidate = work / candidate
            if candidate.is_file() and str(candidate) not in web_assets:
                web_assets.append(str(candidate))
    copied_names: set[str] = set()
    for src in web_assets:
        sp = Path(src)
        if sp.name not in copied_names:
            shutil.copy2(sp, out / "assets" / sp.name)
            copied_names.add(sp.name)
    asset = style.get("web_identity") or style.get("identity_asset")
    image = '<img src="assets/{}" alt="">'.format(Path(asset).name) if asset else ""
    accent_asset = style.get("accent_asset")
    accent_image = '<img class="accent-art" src="assets/{}" alt="">'.format(Path(accent_asset).name) if accent_asset else ""
    sections = "".join('<section><h2 data-type-role="section.heading">{}</h2>{}</section>'.format(
        html_escape(sec["title"]), "".join('<p data-type-role="body">{}</p>'.format(html_escape(p)) for p in sec["paragraphs"])) for sec in content["sections"])
    rows = "".join("<tr>" + "".join("<td>{}</td>".format(html_escape(str(cell))) for cell in row) + "</tr>" for row in content["table"]["rows"])
    headers = "".join("<th scope=\"col\">{}</th>".format(html_escape(x)) for x in content["table"]["columns"])
    cards = "".join('<aside class="card {}"><p class="eyebrow" data-type-role="document.kicker">{}</p><h3 data-type-role="card.title">{}</h3><p data-type-role="body">{}</p></aside>'.format(
        item["kind"].lower(), item["kind"], html_escape(item["title"]), html_escape(item["body"])) for item in content["cards"])
    product = content["product_slick"]
    product_html = '<section class="product-feature"><p class="eyebrow" data-type-role="document.kicker">{}</p><h2 data-type-role="document.title">{}</h2><p class="subtitle" data-type-role="document.subtitle">{}</p><p data-type-role="document.lead">{}</p><ul>{}</ul><p class="scope" data-type-role="annotation">{}</p></section>'.format(
        html_escape(product["eyebrow"]), html_escape(product["title"]), html_escape(product["subtitle"]),
        html_escape(product["description"]), "".join("<li><strong>{}</strong> {}</li>".format(html_escape(item["label"]), html_escape(item["text"])) for item in product["highlights"]),
        html_escape(product["source_note"]))
    one_page = content["one_page"]
    one_page_facts = "".join("<li><strong>{}</strong> {}</li>".format(html_escape(item["label"]), html_escape(item["value"])) for item in one_page.get("facts", []))
    one_page_html = '<section class="one-page-summary"><h2 data-type-role="section.heading">{}</h2><p data-type-role="body">{}</p><ul>{}</ul><p class="scope" data-type-role="annotation">{}</p></section>'.format(
        html_escape(one_page.get("heading", "Brief")), html_escape(one_page["summary"]), one_page_facts, html_escape(one_page.get("source_note", "")))
    html = '''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><meta name="color-scheme" content="light"><title>{title} | {brand}</title><link rel="stylesheet" href="styles.css"></head><body>
<a class="skip" href="#main">Skip to content</a><header><a class="lockup" href="#top">{image}<span data-type-role="identity.wordmark">{brand}</span></a><nav aria-label="On this page"><a href="#brief">Brief</a><a href="#components">Components</a></nav></header>
<main id="main"><section class="hero" id="top"><div><p class="eyebrow" data-type-role="document.eyebrow"><span class="tag">{status}</span><span class="accent-mark" data-type-role="section.marker" aria-hidden="true">{marker}</span></p><h1 data-type-role="document.title">{title}</h1><p class="subtitle" data-type-role="document.subtitle">{subtitle}</p><p class="lead" data-type-role="document.lead">{lead}</p><p class="scope" data-type-role="annotation">{note}</p>{accent_image}</div><div class="hero-figure" role="img" aria-label="Four connected labeled stages: {steps}"><ol>{step_items}</ol><p class="caption" data-type-role="caption">{caption}</p></div></section>
{one_page_html}{product_html}
<section id="brief"><h2 data-type-role="section.heading">Reading the brief</h2>{sections}</section><section id="components"><h2 data-type-role="section.heading">Component matrix</h2><div class="table-wrap"><table><caption data-type-role="caption">{table_caption}</caption><thead><tr>{headers}</tr></thead><tbody>{rows}</tbody></table></div>{cards}</section>
<section><h2 data-type-role="section.heading">References and appendix</h2><ol class="refs">{references}</ol><p data-type-role="annotation">{appendix}</p></section></main><footer><span data-type-role="footer">{brand} / light-context local proof</span><span data-type-role="footer">Browser behavior not reviewed</span></footer></body></html>'''.format(
        title=html_escape(content["title"]), brand=html_escape(style["display_name"]), image=image, accent_image=accent_image,
        status=html_escape(style.get("status_label", "TYPOGRAPHY STUDY")), marker=html_escape(style["accents"].get("marker", "•")),
        subtitle=html_escape(content["subtitle"]), lead=html_escape(content["lead"]), note=html_escape(style.get("note", "Local typesetting proof.")),
        steps=html_escape("; ".join(content["figure"]["steps"])), step_items="".join("<li>{}</li>".format(html_escape(x)) for x in content["figure"]["steps"]),
        caption=html_escape(content["figure"]["caption"]), sections=sections, headers=headers, rows=rows,
        table_caption=html_escape(content["table"]["caption"]), cards=cards,
        one_page_html=one_page_html, product_html=product_html,
        references="".join("<li><strong>{}.</strong> {}</li>".format(html_escape(x["title"]), html_escape(x["detail"])) for x in content["references"]),
        appendix=html_escape(content["appendix"]["intro"]))
    def css_font_source(face: dict[str, Any], fallback_family: str) -> str:
        if face.get("web_file"):
            return 'url("assets/' + Path(face["web_file"]).name + '")'
        return 'local("' + face.get("family", fallback_family) + '")'

    display_src = css_font_source(style["type"]["display"], display)
    body_src = css_font_source(style["type"]["body"], body)
    strong_src = css_font_source(style["type"].get("strong", style["type"]["body"]), body)
    wordmark_src = css_font_source(style["type"].get("wordmark", style["type"]["display"]), display)
    display_weight = style["type"]["display"].get("web_weight", style["type"]["display"].get("weight", 700))
    body_weight = style["type"]["body"].get("web_weight", style["type"]["body"].get("weight", 400))
    strong_weight = style["type"].get("strong", style["type"]["body"]).get("web_weight", style["type"].get("strong", style["type"]["body"]).get("weight", 700))
    wordmark_weight = style["type"].get("wordmark", style["type"]["display"]).get("web_weight", style["type"].get("wordmark", style["type"]["display"]).get("weight", 700))
    mono_css = mono_var = ""
    if "mono" in style["type"]:
        mono_face = style["type"]["mono"]
        mono_family = mono_face.get("family", "monospace")
        mono_src = css_font_source(mono_face, mono_family)
        mono_weight = mono_face.get("web_weight", mono_face.get("weight", 400))
        mono_css = '@font-face {{ font-family: MonoFace; src: {}; font-weight: {}; }}\n'.format(mono_src, mono_weight)
        mono_var = '--mono:MonoFace, "{}", monospace; '.format(mono_family)
    card_radius = {"rounded": "1.25rem", "offset": "1.25rem", "square": "0"}.get(style["accents"].get("card_shape", "square"), "0")
    tag_radius = {"rounded": "999px", "square": "0"}.get(style["accents"].get("tag_shape", "square"), "0")
    role_face_vars = " ".join("--role-{}:var(--{});".format(role.replace(".", "-"), face) for role, face in style["role_map"].items())
    role_selectors = "\n".join('[data-type-role="{}"] {{ font-family:var(--role-{}); }}'.format(role, role.replace(".", "-")) for role in SHARED_TYPE_ROLES)
    css = '''@font-face {{ font-family: DisplayFace; src: {display_src}; font-weight: {display_weight}; }}
@font-face {{ font-family: BodyFace; src: {body_src}; font-weight: {body_weight}; }}
@font-face {{ font-family: StrongFace; src: {strong_src}; font-weight: {strong_weight}; }}
@font-face {{ font-family: WordmarkFace; src: {wordmark_src}; font-weight: {wordmark_weight}; }}
{mono_css}:root {{ --page:#{page}; --card:#{card}; --ink:#{ink}; --muted:#{muted}; --accent:#{accent}; --secondary:#{secondary}; --line:#{line}; --tint:#{tint}; --display:DisplayFace, "{display}", Georgia, serif; --body:BodyFace, "{body}", Georgia, serif; --strong:StrongFace, "{body}", Georgia, serif; --wordmark:WordmarkFace, "{display}", Georgia, serif; {mono_var}{role_face_vars} --card-radius:{card_radius}; --tag-radius:{tag_radius}; }}
* {{ box-sizing:border-box; }} html {{ background:var(--page); scroll-behavior:smooth; }} body {{ margin:0; color:var(--ink); background:var(--page); font:1rem/1.55 var(--body); }}
h1,h2,h3,.tag,.eyebrow {{ font-family:var(--display); }} .lockup span {{ font-family:var(--wordmark); font-weight:{wordmark_weight}; }} strong,b {{ font-family:var(--strong); font-weight:{strong_weight}; }} h1 {{ font-size:clamp(2.35rem,6vw,4.4rem); line-height:1.02; margin:.4em 0; }} h2 {{ font-size:clamp(1.5rem,3vw,2.2rem); color:var(--accent); }} a {{ color:var(--accent); }} a:focus-visible {{ outline:3px solid var(--ink); outline-offset:4px; }}
.skip {{ position:absolute; top:-5rem; left:1rem; background:var(--accent); color:#fff; padding:.7rem 1rem; }} .skip:focus {{ top:1rem; }} header,footer {{ display:flex; justify-content:space-between; align-items:center; gap:1rem; padding:1rem clamp(1.2rem,5vw,4rem); border-bottom:1px solid var(--line); }} .lockup {{ display:flex; align-items:center; gap:.7rem; color:var(--accent); text-decoration:none; font-weight:700; }} .lockup img {{ width:2.2rem; height:auto; }} nav {{ display:flex; gap:1.2rem; flex-wrap:wrap; }} main {{ width:min(100% - 2.4rem,74rem); margin:auto; }} .hero {{ display:grid; grid-template-columns:1.1fr .9fr; gap:3rem; align-items:center; padding:4rem 0; }} .subtitle {{ color:var(--accent); font-size:1.2rem; font-weight:700; }} .lead {{ font-size:1.15rem; }} .scope,.caption,.refs {{ color:var(--muted); }} .tag {{ border:1px solid var(--line); background:var(--tint); color:var(--accent); border-radius:0; padding:.35rem .7rem; font-size:.72rem; letter-spacing:.04em; }} .accent-mark {{ color:var(--secondary); margin-left:1rem; }} .hero-figure {{ padding:2rem; background:var(--card); border:1px solid var(--line); }} .hero-figure ol {{ display:flex; gap:.5rem; list-style:none; padding:0; }} .hero-figure li {{ flex:1; padding:.9rem .5rem; text-align:center; border-top:3px solid var(--accent); background:var(--tint); font-weight:700; }} section {{ margin:3rem 0; }} .table-wrap {{ overflow-x:auto; }} table {{ width:100%; border-collapse:collapse; }} caption {{ text-align:left; color:var(--muted); padding:.6rem 0; }} th,td {{ border-bottom:1px solid var(--line); padding:.7rem .6rem; text-align:left; vertical-align:top; }} th {{ color:var(--accent); background:var(--tint); }} .card {{ margin:1rem 0; padding:1.2rem; background:var(--card); border-left:4px solid var(--accent); }} .card.caution {{ background:var(--tint); border-left-color:var(--secondary); }} .eyebrow {{ color:var(--accent); font-size:.78rem; font-weight:700; letter-spacing:.06em; }} footer {{ margin-top:4rem; border-top:1px solid var(--line); border-bottom:0; color:var(--muted); font-size:.82rem; }}
@media(max-width:700px) {{ header,footer {{ align-items:flex-start; flex-direction:column; }} .hero {{ grid-template-columns:1fr; gap:1rem; padding:2.5rem 0; }} .hero-figure ol {{ flex-direction:column; }} }} @media(prefers-reduced-motion:reduce) {{ html {{ scroll-behavior:auto; }} }}
.accent-art {{ display:block; width:min(5rem,25vw); max-height:3rem; object-fit:contain; object-position:left center; }} .tag {{ border-radius:var(--tag-radius); }} .hero-figure,.card {{ border-radius:var(--card-radius); }}
.product-feature,.one-page-summary {{ margin:2rem 0; padding:1.4rem; border-left:4px solid var(--accent); background:var(--card); }} .product-feature ul,.one-page-summary ul {{ padding-left:1.2rem; }}
@media print {{ html,body {{ background:#fff; }} .skip,nav {{ display:none; }} .hero {{ padding:1.5rem 0; }} .hero-figure,.card,table {{ break-inside:avoid; }} header,footer {{ padding:.5rem 0; }} }}
{role_selectors}'''.format(
        display=display,body=body,display_src=display_src,body_src=body_src,strong_src=strong_src,wordmark_src=wordmark_src,display_weight=display_weight,body_weight=body_weight,strong_weight=strong_weight,wordmark_weight=wordmark_weight,mono_css=mono_css,mono_var=mono_var,role_face_vars=role_face_vars,role_selectors=role_selectors,card_radius=card_radius,tag_radius=tag_radius,page=color("page",colors["page"]),card=color("card",colors.get("card",colors["page"])),ink=color("ink",colors["ink"]),muted=color("muted",colors["muted"]),accent=color("accent",colors["accent"]),secondary=color("secondary",colors.get("secondary",colors["accent"])),line=color("line",colors.get("line",colors["accent"])),tint=color("tint",colors.get("tint",colors["page"])))
    (out / "index.html").write_text(html, encoding="utf-8")
    (out / "styles.css").write_text(css, encoding="utf-8")
    for face in style["type"].values():
        if face.get("web_file"):
            src = Path(face["web_file"])
            shutil.copy2(src, out / "assets" / src.name)
    return {str(p.relative_to(out)): sha256(p) for p in out.rglob("*") if p.is_file()}


def html_escape(value: str) -> str:
    return (value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;").replace("'", "&#39;"))


class _WebAuditParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tags: list[tuple[str, dict[str, str | None]]] = []
        self.ids: set[str] = set()
        self.fragments: list[str] = []
        self.local_refs: list[str] = []
        self.remote_refs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        self.tags.append((tag, values))
        if values.get("id"):
            self.ids.add(values["id"] or "")
        for key in ("href", "src"):
            value = values.get(key) or ""
            if value.startswith("#"):
                self.fragments.append(value[1:])
            elif value and not value.startswith(("data:", "mailto:", "tel:")):
                (self.remote_refs if re.match(r"(?i)^https?://", value) else self.local_refs).append(value)


def verify_web_output(out: Path) -> dict[str, Any]:
    """Check static HTML structure, local references, focus, and responsive CSS."""
    html_path = out / "index.html"
    css_path = out / "styles.css"
    if not html_path.is_file() or not css_path.is_file():
        raise BuildError("Web-light output needs index.html and styles.css")
    markup = html_path.read_text(encoding="utf-8")
    css = css_path.read_text(encoding="utf-8")
    parser = _WebAuditParser()
    parser.feed(markup)
    parser.close()
    tags = [tag for tag, _ in parser.tags]
    if not re.search(r"<html\b[^>]*\blang=\"en\"", markup, re.I):
        raise BuildError("Web-light output must declare an English document language")
    if not re.search(r"<meta\b[^>]*name=\"viewport\"", markup, re.I):
        raise BuildError("Web-light output must declare a responsive viewport")
    if tags.count("h1") != 1 or "main" not in tags or "header" not in tags or "footer" not in tags:
        raise BuildError("Web-light output needs one h1 and semantic header, main, and footer")
    if not any(tag == "a" and attrs.get("class") == "skip" for tag, attrs in parser.tags):
        raise BuildError("Web-light output needs a skip-to-content link")
    if any(fragment not in parser.ids for fragment in parser.fragments):
        raise BuildError("Web-light output has an unresolved local fragment link")
    if parser.remote_refs:
        raise BuildError("Web-light output must not depend on remote links or assets")
    for ref in parser.local_refs:
        if not (out / ref.split("#", 1)[0]).is_file():
            raise BuildError("Web-light output has a missing local asset: {}".format(ref))
    font_urls = re.findall(r"url\([\"']?([^\"')]+)", css)
    if any(url.startswith(("http:", "https:")) for url in font_urls):
        raise BuildError("Web-light CSS must not load remote fonts")
    for url in font_urls:
        if not (out / url.split("#", 1)[0]).is_file():
            raise BuildError("Web-light CSS has a missing local font asset: {}".format(url))
    if not re.search(r"@media\s*\(\s*max-width", css):
        raise BuildError("Web-light CSS needs a responsive narrow-screen layout")
    if ":focus-visible" not in css:
        raise BuildError("Web-light CSS needs a visible keyboard focus state")
    if "scroll-behavior:smooth" in css.replace(" ", "") and "prefers-reduced-motion:reduce" not in css.replace(" ", ""):
        raise BuildError("Web-light smooth scrolling must respect reduced motion")
    missing_roles = [role for role in SHARED_TYPE_ROLES if '[data-type-role="{}"]'.format(role) not in css]
    if missing_roles:
        raise BuildError("Web-light CSS is missing semantic type role selectors: {}".format(", ".join(missing_roles)))
    return {
        "semantic_landmarks": True,
        "one_primary_heading": True,
        "skip_link_and_fragments_resolve": True,
        "responsive_narrow_screen_rule": True,
        "keyboard_focus_visible": True,
        "reduced_motion_handled": True,
        "local_assets_resolve": True,
        "shared_type_role_selectors": len(SHARED_TYPE_ROLES),
        "remote_dependencies": 0,
        "browser_verified": False,
    }


def normalize_pdf_text(value: str) -> str:
    quotes = str.maketrans({"’": "'", "‘": "'", "“": '"', "”": '"', "–": "-", "—": "-"})
    return " ".join(value.translate(quotes).split())


def pdf_page_count(pdf: Path, cwd: Path) -> int:
    info = run([shutil.which("pdfinfo") or "pdfinfo", str(pdf)], cwd)
    match = re.search(r"^Pages:\s+(\d+)\s*$", info, re.M)
    if not match:
        raise BuildError("Could not read page count from {}".format(pdf))
    return int(match.group(1))


def verify_srgb_output_intent(pdf: Path, expected_icc: Path | None = None) -> dict[str, Any]:
    """Resolve the PDF catalog's sRGB intent and compare the embedded ICC bytes."""
    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover - installation-specific
        raise BuildError("sRGB verification needs pypdf; install the optional PDF-render dependencies") from exc
    try:
        reader = PdfReader(str(pdf), strict=True)
        intents = reader.trailer["/Root"].get("/OutputIntents")
        if intents is None or len(intents) != 1:
            raise BuildError("PDF must contain exactly one catalog OutputIntent")
        intent = intents[0].get_object()
        if str(intent.get("/Type")) != "/OutputIntent":
            raise BuildError("Catalog entry is not a PDF OutputIntent")
        if str(intent.get("/S")) != "/GTS_PDFA1":
            raise BuildError("OutputIntent does not use the declared ICC profile subtype")
        if str(intent.get("/OutputConditionIdentifier")) != "sRGB IEC61966-2.1":
            raise BuildError("OutputIntent does not identify sRGB IEC61966-2.1")
        profile_ref = intent.get("/DestOutputProfile")
        if profile_ref is None:
            raise BuildError("OutputIntent has no destination profile stream")
        profile = profile_ref.get_object()
        profile_bytes = profile.get_data()
        if int(profile.get("/N", 0)) != 3:
            raise BuildError("OutputIntent profile must declare three colour components")
        if expected_icc is not None and profile_bytes != expected_icc.read_bytes():
            raise BuildError("Embedded OutputIntent profile does not match the supplied ICC bytes")
        return {
            "output_condition": str(intent["/OutputConditionIdentifier"]),
            "profile_components": int(profile["/N"]),
            "profile_bytes": len(profile_bytes),
            "profile_sha256": hashlib.sha256(profile_bytes).hexdigest(),
        }
    except BuildError:
        raise
    except Exception as exc:
        raise BuildError("Could not resolve the PDF sRGB OutputIntent: {}".format(exc)) from exc


def has_srgb_output_intent(pdf: Path, expected_icc: Path | None = None) -> bool:
    try:
        verify_srgb_output_intent(pdf, expected_icc)
    except BuildError:
        return False
    return True


def build(style_path: Path, content_path: Path, output_override: Path | None = None,
          only_outputs: tuple[str, ...] | None = None, include_web: bool = True) -> dict[str, Any]:
    style, content = read_json(style_path), read_json(content_path)
    if "recipe_version" in style:
        from build_recipe_suite import build as build_recipe
        return build_recipe(style_path, content_path, output_override, only_outputs, include_web)
    manifest_dir = style_path.parent
    for source in style.get("sources", []):
        path = Path(source["path"])
        if not path.is_absolute(): source["path"] = str((manifest_dir / path).resolve())
    for face in style.get("type", {}).values():
        path = Path(face["path"])
        if not path.is_absolute(): face["path"] = str((manifest_dir / path).resolve())
        if face.get("web_file"):
            path = Path(face["web_file"])
            if not path.is_absolute(): face["web_file"] = str((manifest_dir / path).resolve())
    for item in style.get("licenses", []):
        path = Path(item["path"])
        if not path.is_absolute(): item["path"] = str((manifest_dir / path).resolve())
    for key in ("identity_asset", "print_identity_asset", "web_identity", "accent_asset", "srgb_icc"):
        if style.get(key):
            path = Path(style[key])
            if not path.is_absolute(): style[key] = str((manifest_dir / path).resolve())
    style["web_assets"] = [str((manifest_dir / p).resolve()) if not Path(p).is_absolute() else p for p in style.get("web_assets", [])]
    validate_manifest(style, content)
    selected_outputs = OUTPUTS if only_outputs is None else only_outputs
    if not selected_outputs or len(set(selected_outputs)) != len(selected_outputs) or not set(selected_outputs).issubset(OUTPUTS):
        raise BuildError("Selected PDF outputs must be a non-empty, unique subset of {}".format(", ".join(OUTPUTS)))
    out = (output_override or Path(style["output_dir"])).resolve()
    if out.exists():
        raise BuildError("Output directory already exists; choose a new private destination: {}".format(out))
    work = out / "editable-source"
    pdf_dir = out / "pdf"
    web_dir = out / "web-light"
    output_dirs = (work, pdf_dir, web_dir) if include_web else (work, pdf_dir)
    for d in output_dirs:
        d.mkdir(parents=True, exist_ok=False)
    original_sources = []
    for source in style["sources"]:
        src = Path(source["path"]).resolve()
        # Assets are copied only into this private output bundle.
        dest = work / "assets" / source.get("bundle_name", src.name)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        original_sources.append({"path": str(src), "bundle_path": str(dest.relative_to(work)), "sha256": sha256(src),
                                 "rights": source.get("rights"), "use": source.get("use")})
    srgb_source = Path(style["srgb_icc"]).resolve()
    assets_dir = work / "assets"
    assets_dir.mkdir(exist_ok=True)
    shutil.copy2(srgb_source, assets_dir / "sRGB.icc")
    # Place working copies of typefaces beside the TeX. Paid faces stay out of the ZIP.
    work_fonts = work / "fonts"
    work_fonts.mkdir(exist_ok=True)
    for face in style["type"].values():
        src = Path(face["path"]).resolve()
        dest = work_fonts / (face.get("filename") or src.name)
        if not dest.exists():
            shutil.copyfile(src, dest)
        face["source_path"] = str(src)
        face["path"] = "fonts/" + dest.name
        face["build_path"] = str(dest.resolve())
    style["source_identity_asset"] = style.get("identity_asset")
    style["source_print_identity_asset"] = style.get("print_identity_asset")
    style["source_web_identity"] = style.get("web_identity")
    style["source_accent_asset"] = style.get("accent_asset")
    if style.get("identity_asset"):
        style["identity_asset"] = "assets/" + Path(style["identity_asset"]).name
    if style.get("print_identity_asset"):
        source = Path(style["print_identity_asset"]).resolve()
        staged = work / "assets" / source.name
        if source.resolve() != staged.resolve():
            shutil.copy2(source, staged)
        style["print_identity_asset"] = "assets/" + source.name
    if style.get("accent_asset"):
        style["accent_asset"] = "assets/" + Path(style["accent_asset"]).name
    if style.get("web_identity"):
        style["web_identity"] = "assets/" + Path(style["web_identity"]).name
    style["srgb_icc"] = "assets/sRGB.icc"
    style["sources"] = [{"bundle_path": item["bundle_path"], "sha256": item["sha256"], "rights": item["rights"], "use": item["use"]} for item in original_sources]
    (work / "style.json").write_text(json.dumps(style, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    shutil.copy2(content_path, work / "content.json")
    source_records = content.get("source_records", [])
    content_source = {"path": str(content_path.resolve()), "sha256": sha256(content_path), "records": source_records}
    (work / "source-register.json").write_text(json.dumps({"inputs": original_sources,
        "font_sources": [{"role": k, "source_path": v["source_path"], "sha256": sha256(Path(v["source_path"]))} for k,v in style["type"].items()],
        "srgb_icc": {"source_path": str(srgb_source), "sha256": sha256(srgb_source)},
        "content_source": content_source,
        "profile_version": style["profile_version"]}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    for mode in selected_outputs:
        source = work / (mode + ".tex")
        body = component_proof(style, content) if mode == "component-proof" else compact_document(style, content, mode)
        source.write_text(tex_preamble(style, mode, work) + body, encoding="utf-8")
        # Use the private work directory so local assets and fonts remain relative.
        staged_dir = work / "compiled"
        staged_dir.mkdir(exist_ok=True)
        pdf_name = mode + ".pdf"
        expected = style.get("pdf_page_counts", {}).get(mode, {"one-page": 1, "two-page": 2, "product-slick": 1}.get(mode))
        log_output = run([shutil.which("tectonic") or "tectonic", "--only-cached", "--keep-logs", "--keep-intermediates", "--outdir", str(staged_dir), str(source)], work)
        # The TOC and cross-references settle on the second pass.
        if mode == "component-proof":
            log_output += run([shutil.which("tectonic") or "tectonic", "--only-cached", "--keep-logs", "--keep-intermediates", "--outdir", str(staged_dir), str(source)], work)
        pdf = staged_dir / pdf_name
        if not pdf.is_file():
            raise BuildError("Tectonic did not create {}".format(pdf))
        log_path = staged_dir / (mode + ".log")
        log = log_path.read_text(encoding="utf-8", errors="replace") if log_path.exists() else log_output
        errors = BAD_TEX.findall(log)
        if errors:
            raise BuildError("{} contains TeX/font layout errors: {}".format(mode, " | ".join(errors[:10])))
        pages = pdf_page_count(pdf, work)
        if expected and pages != expected:
            raise BuildError("{} has {} pages; expected {}".format(mode, pages, expected))
        if style.get("require_srgb_output_intent"):
            verify_srgb_output_intent(pdf, assets_dir / "sRGB.icc")
        extracted = run([shutil.which("pdftotext") or "pdftotext", str(pdf), "-"], work)
        normalized_text = normalize_pdf_text(extracted)
        required_title = content["product_slick"]["title"] if mode == "product-slick" else content["title"]
        for required in (required_title, style.get("status_label", "TYPOGRAPHY STUDY")):
            if normalize_pdf_text(required) not in normalized_text:
                raise BuildError("{} is missing required text {!r}".format(mode, required))
        if "??" in normalized_text:
            raise BuildError("{} contains unresolved cross-references".format(mode))
        fonts = run([shutil.which("pdffonts") or "pdffonts", str(pdf)], work)
        font_lines = [line for line in fonts.splitlines()[2:] if line.strip() and not line.startswith("-")]
        if not font_lines or any(line.split()[-5:-2] != ["yes", "yes", "yes"] for line in font_lines):
            raise BuildError("{} has unembedded fonts:\n{}".format(mode, fonts))
        shutil.copy2(pdf, pdf_dir / pdf_name)
        if log_path.exists():
            shutil.copy2(log_path, work / (mode + ".log"))
    web_hashes = html_document(style, content, web_dir, work) if include_web else None
    web_checks = verify_web_output(web_dir) if include_web else None
    report = {
        "schema_version": 1, "family_id": style["family_id"], "display_name": style["display_name"],
        "profile_version": style["profile_version"], "status": style["status"], "context": style.get("context", "light"),
        "route": style.get("route"), "source_register": style["sources"],
        "font_provenance": [{"role": k, "family": v.get("family"), "source": v.get("source_path"), "sha256": sha256(Path(v["source_path"]))} for k,v in style["type"].items()],
        "type_role_map": style["role_map"],
        "pdfs": {p.stem: {"path": str(p.relative_to(out)), "pages": pdf_page_count(p, out), "bytes": p.stat().st_size, "sha256": sha256(p), "srgb_output_intent": has_srgb_output_intent(p, assets_dir / "sRGB.icc"), "srgb_output_intent_detail": verify_srgb_output_intent(p, assets_dir / "sRGB.icc") if style.get("require_srgb_output_intent") else None, "embedded_fonts": True} for p in sorted(pdf_dir.glob("*.pdf"))},
        "web": ({"path": "web-light/index.html", "static_only": True, "browser_verified": False, "static_checks": web_checks, "files": web_hashes}
                if include_web else {"omitted_for_bounded_review": True}),
        "limits": style.get("limits", []), "source_provenance": style.get("source_provenance", {}),
        "content_provenance": content_source,
        "typography_notes": style.get("typography_notes", ""), "accent_system": style.get("accents", {}),
        "selected_outputs": list(selected_outputs),
    }
    (out / "build-report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    # Editable package: omit fonts whose manifest does not explicitly permit bundling.
    package_sources = work / "package-source"
    package_sources.mkdir(exist_ok=True)
    for name in ("style.json", "content.json", "one-page.tex", "two-page.tex", "product-slick.tex", "component-proof.tex", "source-register.json"):
        src = work / name
        if src.exists(): shutil.copy2(src, package_sources / name)
    bundle_fonts = bool(style.get("bundle_fonts", False))
    portable_style = json.loads(json.dumps(style))
    for face in portable_style["type"].values():
        face.pop("source_path", None)
        face.pop("build_path", None)
        if not bundle_fonts:
            face.pop("web_file", None)
        elif face.get("web_file"):
            face["web_file"] = "fonts/" + Path(face["web_file"]).name
    portable_style["sources"] = [{"path": item["bundle_path"], "sha256": item["sha256"],
                                   "rights": item["rights"], "use": item["use"]} for item in original_sources]
    portable_style["identity_asset"] = "assets/" + Path(style["source_identity_asset"]).name if style.get("source_identity_asset") else None
    portable_style.pop("source_identity_asset", None)
    portable_style["print_identity_asset"] = "assets/" + Path(style["source_print_identity_asset"]).name if style.get("source_print_identity_asset") else None
    portable_style.pop("source_print_identity_asset", None)
    portable_style["web_identity"] = "assets/" + Path(style["source_web_identity"]).name if style.get("source_web_identity") else None
    portable_style.pop("source_web_identity", None)
    portable_style["accent_asset"] = "assets/" + Path(style["source_accent_asset"]).name if style.get("source_accent_asset") else None
    portable_style.pop("source_accent_asset", None)
    portable_style["srgb_icc"] = "assets/sRGB.icc"
    portable_style["web_assets"] = ["assets/" + Path(p).name for p in style.get("web_assets", [])]
    portable_style["licenses"] = [{"path": "licenses/" + Path(item["path"]).name} for item in style.get("licenses", [])]
    portable_style["output_dir"] = "proof-output"
    (package_sources / "style.json").write_text(json.dumps(portable_style, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    shutil.copy2(out / "build-report.json", package_sources / "build-report.json")
    if include_web:
        shutil.copytree(web_dir, package_sources / "web-light", dirs_exist_ok=True)
    if style.get("include_pdf_in_package", True):
        (package_sources / "pdf").mkdir(exist_ok=True)
        for pdf in pdf_dir.glob("*.pdf"):
            shutil.copy2(pdf, package_sources / "pdf" / pdf.name)
    if bundle_fonts:
        shutil.copytree(work_fonts, package_sources / "fonts", dirs_exist_ok=True)
        (package_sources / "licenses").mkdir(parents=True, exist_ok=True)
        for item in style.get("licenses", []):
            shutil.copy2(item["path"], package_sources / "licenses" / Path(item["path"]).name)
    if (work / "assets").exists():
        shutil.copytree(work / "assets", package_sources / "assets", dirs_exist_ok=True)
    if (web_dir / "assets").exists():
        shutil.copytree(web_dir / "assets", package_sources / "assets", dirs_exist_ok=True)
    web_note = ("Web output is static source; browser behavior is not verified." if include_web else
                "Web-light output was omitted from this bounded proof build.")
    readme = ["# {} typography proof package".format(style["display_name"]), "",
              "Profile version: `{}`. Status: `{}`. Context: `{}`.".format(style["profile_version"], style["status"], style.get("context", "light")),
              "", "The selected PDF proofs use shared semantic roles and reusable components with family-owned layout, fonts, colors and accents. {}".format(web_note),
              "", "Rebuild with `python build_family_typesetting_suite.py --style style.json --content content.json --output-dir rebuilt` after placing the declared fonts under `fonts/` and required assets under `assets/`.",
              "", "Font files are included only where the source manifest permits bundling. Commercial fonts are omitted; their presence in a generated PDF does not authorize redistribution.",
              "", "Screen proof only. No press, accessibility, launch, or whole-brand approval is implied.", ""]
    (package_sources / "README.md").write_text("\n".join(readme), encoding="utf-8")
    zip_path = out / (style["family_id"] + "_Typography_Proofs_0_1.zip")
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(package_sources.rglob("*")):
            if path.is_file(): archive.write(path, path.relative_to(package_sources))
    return report | {"output_dir": str(out), "editable_source_zip": str(zip_path), "zip_bytes": zip_path.stat().st_size, "zip_sha256": sha256(zip_path)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--style", type=Path, required=True, help="family-owned style manifest")
    parser.add_argument("--content", type=Path, required=True, help="content fixture with source notes")
    parser.add_argument("--output-dir", type=Path, help="override the output directory from the private style manifest")
    parser.add_argument("--only", action="append", help="build selected PDF output IDs (repeatable; validated by the selected recipe)")
    parser.add_argument("--no-web", action="store_true", help="omit web-light output for a bounded PDF review")
    args = parser.parse_args()
    try:
        report = build(args.style.resolve(), args.content.resolve(), args.output_dir.absolute() if args.output_dir else None,
                       tuple(args.only) if args.only else None, not args.no_web)
    except (BuildError, OSError, KeyError, ValueError, zipfile.BadZipFile) as exc:
        print("Family typesetting build rejected: {}".format(exc), file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
