# Third-party licenses

PHOTOSHEET uses the following components. Their licenses are independent of this program's MIT + Commons Clause terms.

| Component | Version | License |
| --- | --- | --- |
| Streamlit | 1.40.1 | Apache License 2.0 |
| Pillow | 11.3.0 | MIT-CMU / HPND (PIL license); bundled codecs retain their own notices |
| openpyxl | 3.1.5 | MIT License |
| SUIT Regular / SemiBold | bundled font files | SIL Open Font License 1.1, SUIT project / SUNN; https://github.com/sunn-us/SUIT |

Dependencies installed by pip (Streamlit, Pillow, openpyxl) keep their own license notices in the Python environment. The SUIT font files in `static/fonts/` are distributed under the SIL Open Font License; its full text is included below. Python is licensed under the Python Software Foundation terms.

Development and verification only: pytest 8.4.2 (MIT), Playwright 1.55.0 (Apache 2.0), PyMuPDF 1.26.5 (AGPL-3.0; separately installed verification tool), LibreOffice (MPL 2.0 and upstream component terms). These tools are not imported by the runtime app or bundled with the release. PyMuPDF is used only to render the requested PDF proof images locally.

SUIT fonts may be used, embedded and redistributed under the SIL OFL 1.1; a modified font must observe reserved font name conditions. The font files are redistributed unchanged from the local reference project. No font is licensed under PHOTOSHEET's Commons Clause.

Demo photographs were generated with the built-in image generation tool for this fictional demonstration; they are not documentary evidence of a real site.

## SUIT font — SIL Open Font License 1.1

```
SUIT font — SUIT Project / SUNN
Upstream: https://github.com/sunn-us/SUIT
The original copyright and reserved font name records embedded in the
unmodified SUIT font files remain in force.

SIL OPEN FONT LICENSE Version 1.1 - 26 February 2007

PREAMBLE
The goals of the Open Font License (OFL) are to stimulate worldwide
development of collaborative font projects, to support the font creation
efforts of academic and linguistic communities, and to provide a free and
open framework in which fonts may be shared and improved in partnership
with others.

The OFL allows the licensed fonts to be used, studied, modified and
redistributed freely as long as they are not sold by themselves. The
fonts, including any derivative works, can be bundled, embedded,
redistributed and/or sold with any software provided that any reserved
names are not used by derivative works. The fonts and derivatives,
however, cannot be released under any other type of license. The
requirement for fonts to remain under this license does not apply
to any document created using the fonts or their derivatives.

DEFINITIONS
"Font Software" refers to the set of files released by the Copyright
Holder(s) under this license and clearly marked as such. This may
include source files, build scripts and documentation.

"Reserved Font Name" refers to any names specified as such after the
copyright statement(s).

"Original Version" refers to the collection of Font Software components as
distributed by the Copyright Holder(s).

"Modified Version" refers to any derivative made by adding to, deleting,
or substituting -- in part or in whole -- any of the components of the
Original Version, by changing formats or by porting the Font Software to a
new environment.

"Author" refers to any designer, engineer, programmer, technical
writer or other person who contributed to the Font Software.

PERMISSION & CONDITIONS
Permission is hereby granted, free of charge, to any person obtaining
a copy of the Font Software, to use, study, copy, merge, embed, modify,
redistribute, and sell modified and unmodified copies of the Font
Software, subject to the following conditions:

1) Neither the Font Software nor any of its individual components,
in Original or Modified Versions, may be sold by itself.

2) Original or Modified Versions of the Font Software may be bundled,
redistributed and/or sold with any software, provided that each copy
contains the above copyright notice and this license. These can be
included either as stand-alone text files, human-readable headers or
in the appropriate machine-readable metadata fields within text or
binary files as long as those fields can be easily viewed by the user.

3) No Modified Version of the Font Software may use the Reserved Font
Name(s) unless explicit written permission is granted by the corresponding
Copyright Holder. This restriction only applies to the primary font name as
presented to the users.

4) The name(s) of the Copyright Holder(s) or the Author(s) of the Font
Software shall not be used to promote, endorse or advertise any
Modified Version, except to acknowledge the contribution(s) of the
Copyright Holder(s) and the Author(s) or with their explicit written
permission.

5) The Font Software, modified or unmodified, in part or in whole,
must be distributed entirely under this license, and must not be
distributed under any other license. The requirement for fonts to
remain under this license does not apply to any document created
using the Font Software.

TERMINATION
This license becomes null and void if any of the above conditions are
not met.

DISCLAIMER
THE FONT SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO ANY WARRANTIES OF
MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT
OF COPYRIGHT, PATENT, TRADEMARK, OR OTHER RIGHT. IN NO EVENT SHALL THE
COPYRIGHT HOLDER BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY,
INCLUDING ANY GENERAL, SPECIAL, INDIRECT, INCIDENTAL, OR CONSEQUENTIAL
DAMAGES, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
FROM, OUT OF THE USE OR INABILITY TO USE THE FONT SOFTWARE OR FROM
OTHER DEALINGS IN THE FONT SOFTWARE.
```
