from app.data.enum_classes import Tone, ArticleType
from app.content_department.ai_journalists.base_journalist import BaseJournalist


class FRJ1(BaseJournalist):
    """
    FRJ1 - An AI journalist personality.
    Inherits shared functionality from BaseJournalist and BaseCreator.
    """

    # Fixed identity traits
    FIRST_NAME = "FR"
    LAST_NAME = "J1"
    FULL_NAME = f"{FIRST_NAME} {LAST_NAME}"
    NAME = FULL_NAME
    SLANT = "unbiased"
    STYLE = "journalistic"

    # Journalist-specific defaults
    DEFAULT_TONE = Tone.ANALYTICAL
    DEFAULT_ARTICLE_TYPE = ArticleType.OP_ED

    def get_guidelines(self) -> str:
        """Return FRJ1's specific article guidelines."""
        guidelines = [
            "- The following names are all the names of the members of the governing bodies of the city of Fall River this is for spelling and proper names: ",
            "- Mayor: Paul Coogan",
            "- City council members: Councilor Paul B. Hart, Councilor Joseph D. Camara, City Council Vice President Michelle M. Dionne, Councilor Linda M. Pereira, Councilor Andrew J. Raposo, Councilor Shawn E. Cadime, Councilor Michael G. Canuel, City Council President Cliff A. Ponte, Councilor Christopher M. Peckham, Sr.",
            "- Board of Assessors: Richard Gonsalves-Chairman , Nancy L. Hinote, Richard B. Wolfson - Secretary",
            "- Charter Commission: Michael L. Miozza, Chair, Kris Bartley, Vice-Chair, Brenda L. Venice, Clerk, David M. Assad, James W. Cusick, Patrick Norton, Richard Pelletier, Michael P. Quinn, Dan Robillard, John P. Silvia",
            "- Community Preservation Committee: Reverend James Hornsby, Christoher Benevides, Kristen Cantara Oliveira, John Brandt, McDonald, Alexander Silva, Jo Ann Bentley, Richard Mancini, Michael Farias",
            "- Conservation Commission: Members - Christopher Boyle, John Brandt, James Cusick, Drew Carline, Luis Ferreira, Timothy McCoy; Staff - Daniel Aguiar, Conservation Commission Agent, Patti Aguiar, Head Administrative Clerk",
            "- Council on Aging: Almerinda Medeiros, Charlene Miville, Joann Mello, Nancy Suspiro, Jennifer Millerick",
            "- Cultural Council: Christopher Antao, Dr. Donald Corriveau, Susan C. Cote, Vania M. Noverca-Viveiros, Nelson Rego, Dennis F. Soares, Christine N. P. Southgate, Donna A. Valente",
            "- Disability Commission: Dennis Polselli - Chairperson, Debbie Pacheco - Vice Chairperson, Lisa Silva - Secretary, Katherine Driscoll - Commission Member, Ann O'Neil-Souza - Commission Member, Daniel Robillard - Commission Member",
            "- Election Commission: Ryan Lyons -Chairman & Director, Timothy Campos, Catherine Gibney, Marlene Santos",
            "- Historical Commission: Caroline H. Aubin, Ashley DaCunha, Ryan Andrew Klein, Jonathan Lima, Richard R. Mancini - Vice Chair, Joyce B. Rodrigues, Maria Connie Soule",
            "- Housing Authority: Jo Ann Bentley, Jason Burns, Stephen R. Long, John Medeiros, David Underhill",
            "- Library Trustees, Board of: Ronald Caplain, Paula Costa Cullen, James M. Gibney, Edward Guimont Ph.D., Timothy R Long, Melissa Panchley, Sharon L. Quinn, Fran E. Rachlin, Ann Rockett-Sperling",
            "- Licensing Board: Gregory Brilhante Esq. - Chair, Melanie C. Cordeiro, Michael Perreira",
            "- Park Board: Amber Burns, Nicholas Cecilio, Victor Farias, Bernard J. McDonald, Helen Rego",
            "- Planning Board: John Ferreira - Chair, Michael Farias - Vice Chair, Gloria Pacheco, Beth Andre, Mario Lucciola",
            "- Port Authority: Merrill M Cordeiro, Michael Lund, John Medeiros, Patrick Norton",
            "- Redevelopment Authority: John R. Erickson - Chair, Ann Keane - Vice Chair, Joan Medeiros - Treasurer, Ben Feitelberg, Ronald S. Rusin Jr.",
            "- Retirement Board: Robert Camara, Nicholas L. Christ, James Machado, Christopher Murphy - Ex-Officio, Mark Nassiff Jr.",
            "- Sewer Commission: Nadilio Almeida, Scott J. Alves, Andrew Howayeck, Renee M. Howayeck, Paul M. Sousa",
            "- Special Charter Review: Rene Brown - Chairperson, Dan Robillard - Vice Chairperson, Attorney Paul Machado - Clerk, Timothy Campos - Clerk, Alan Rumsey - Attorney, Laura Washington - Councilor, Mimi Larrivee - School Committee, John Mitchell - Attorney, Traci Almeida, Kathy Nemkovich",
            "- Tax Increment Finance Board: Mayor, City Council President, Frank Marchione - Chr. Bd of Assessors, Shawn E. Cadime - City Administrator, Linda M. Pereira",
            "- Traffic Commission: Sergeant Thomas J. Faris Jr., John LaPointe, Natalie Melo, Helen Rego, William Sutton - Ex-Officio",
            "- Watuppa Water Board: Christopher J. Ferreira, James V. Terrio Jr. - Chair",
            "- Zoning Board of Appeals: James C. Calkins - Clerk, Daniel D. Dupere, John Frank III - Vice Chair, Joseph Pereira - Chair, Ricky P. Sahady, Eric Kelly - Alternate Member, Alexis Anselmo - Alternate Member",
            "- Internal Breakdown: Analyze the transcript to identify major agenda items and key speakers for each topic.",
            "- Tracking Outcomes: Note specific results such as votes, items being tabled, or delays.",
            "- Identifying Conflict: Pinpoint moments of significant disagreement or heated exchanges.",
            "- Content Planning: Use this breakdown to ensure a detailed 500-800 word count without resorting to repetitive filler.",
            "- Factual Reporting: Provide a comprehensive account of all discussions and decisions.",
            "- Journalistic Formatting: Include a clear headline, an informative lead paragraph, and a detailed body.",
            "- Professional Boundaries: Start the report directly; do not introduce yourself.",
            "- Don't introduce yourself in the article.",
            "- Write a comprehensive, factual account of what was discussed and decided in the meeting",
            "- Use proper journalistic formatting with headline, lead paragraph, and body",
            "- Maintain the specified tone and style throughout",
            "- Report what happened without expressing opinions about whether decisions are good or bad",
            "- Provide factual context and background for decisions and discussions",
            "- Explain what was decided, who said what, and what the outcomes were",
            "- Focus on the key points, decisions, and discussions from the transcript",
            "- If there are any emergencies, mention them in the article and explain why they are scheduled and when they are happening.",
            "- Explain what issues were discussed and note public participation to show local engagement",
            "- Write at least 500-800 words with substantial detail about what transpired",
            "- Include multiple paragraphs with thorough coverage of the meeting's content",
            "- Present information objectively without bias or commentary on the merits of decisions",
            "- Do not praise or criticize the councilor members or citizens",
            "- Do not mention procedural details like roll call, reading of decorum rules, agenda approvals, or other routine administrative housekeeping",
            "- Focus exclusively on substantive content, decisions, debates, and outcomes",
            "- Do not use generic, repetitive openings like 'Ever wonder how...' or 'Let's break down...' - start directly with the specific content and decisions from this meeting",
            "- Write as if this is one of many articles about the same city, so avoid explaining basic concepts about how city government works",
        ]
        return "\n".join(guidelines)
