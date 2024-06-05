from asyncio import get_event_loop
#from ..database.conjugations import Conjugation
#from ..database.verbs import Verb, Reflexivity

import json
import logging

from fix_busted_json import repair_json

from openai import OpenAI, ChatCompletion
from openai import AsyncOpenAI

from sqlalchemy import and_, select, insert, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import sessionmaker

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from ..database.engine import Base
from ..database.engine import async_engine
from ..database.verbs import Reflexivity


log = logging.getLogger(__name__)

client:    OpenAI = AsyncOpenAI()
openai_model: str = "gpt-3.5-turbo"
openai_role:  str = "user"

AsyncSessionLocal = async_sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    expire_on_commit=False
)

@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

auxiliaries: list[str] = [ "avoir", "être" ]

def generate_tense_list_prompt(verb_infinitive: str) -> str:
    return ""

def generate_reflexivity_prompt(verb_infinitive: str) -> str: 
    return """If the verb can only be used reflexively then return 'mandatory', \
              if the verb can be used both reflexive and non-reflexively return \
              'conditional', otherwise return 'no'."""

def generate_verb_tense_format(verb: str) -> str:
    return """ \
                {   \
                    verb tense (as tense): \
                    conjugations: [ \
                        {  \
                            french pronoun (as 'pronoun'): \
                            conjugated verb, without its pronoun (as 'verb'):    \
                            english translation (as 'translation'): \
                        }  \
                    ]   \
                } \
"""

def generate_extra_rules(verb_infinitive: str) -> str:
    return """Do not return any newlines in the response. \
            Always use both genders in the 3rd person pronouns.  \
            Always include 'on' for the 3rd person singular form.  \
            Replace spaces with _ in the tense names. \
            Remove all accent marks on the tense names. \
            The first person pronoun should always be 'je' instead of j' or j. \
            The pronouns should always be "-" for participles. \
            All json property names and values need to be enclosed in double quotes. \
            """

def generate_verb_prompt(verb_infinitive: str):
    return f"""Give me the present, passé composé (as passe_compose), imparfait, future simple tense, \
            and past participle (as participle), and auxiliary verb of the French verb {verb_infinitive}, \
            with english translations, with each verb mode being a json object of the format: \
                auxiliary: \
                infinitive: {verb_infinitive} \
                reflexivity: {generate_reflexivity_prompt(verb_infinitive)} \
                verb tense (as 'tenses'): [ \
                    {generate_verb_tense_format(verb_infinitive)} \
                ] \
            {generate_extra_rules(verb_infinitive)}
            """

async def fetch_verb(requested_verb: str, save_verb: bool) -> str:
    
    Conjugation = Base.classes.conjugations
    Verb = Base.classes.verbs
    
    print(Conjugation.__table__.columns)
    print(Verb.__table__.columns)
    
    log.info(f"Fetching verb {requested_verb}")

    completion: ChatCompletion = await client.chat.completions.create(
        model    = openai_model,
        messages = [
            { "role": openai_role, "content": generate_verb_prompt(requested_verb) },
        ]
    )

    if save_verb:
        async with get_session() as session:

            print(f"Saving this verb {requested_verb}")

            response: str = repair_json(completion.choices[0].message.content)
            response_json: str = json.loads(response)
            
            print(response_json)
            
            infinitive: str = response_json["infinitive"]

            existing_verb: Verb = (
                await session.scalars(select(Verb)
                    .filter(Verb.infinitive == requested_verb)
                    .order_by(Verb.id.desc()))).first()

            if existing_verb != None:
                log.info(f"The verb {infinitive} already exists and will be updated if needed.")
            else:
                log.info(f"The verb {infinitive} does not yet exist in the database.")

            verb: Verb = Verb() if existing_verb == None else existing_verb
            verb.auxiliary   = response_json["auxiliary"]
            verb.infinitive  = infinitive
            verb.reflexivity = Reflexivity[response_json["reflexivity"]]

            session.add(verb)       
                
            for response_tense in response_json["tenses"]:

                tense = response_tense["tense"]
                print(tense)
                                
                existing_conjugation: Conjugation = (
                    await session.scalars(select(Conjugation)
                        .filter(and_(Conjugation.infinitive == infinitive, Conjugation.tense == tense))
                        .order_by(Conjugation.id.desc()))).first()

                if existing_conjugation != None:
                    log.info(f"A verb conjugation for {infinitive}, {tense} already exists and will be updated.")
                else:
                    log.info(f"Verb conjugations are missing or are incomplete for {infinitive} and will be added/updated.")

                conjugation: Conjugation = Conjugation() if existing_conjugation == None else existing_conjugation
                conjugation.infinitive   = infinitive
                conjugation.tense        = tense
                conjugation.verb_id      = verb.id

                for response_conjugation in response_tense["conjugations"]:

                    #   Should only set if response is not null to account for ChatGTP non-determinism:
                    match response_conjugation["pronoun"]:
                        case "je" | "j'" | "j":
                            conjugation.first_person_singular = response_conjugation["verb"]
                        case "tu":
                            conjugation.second_person_singular = response_conjugation["verb"]
                        case "il/elle/on" | "il" | "elle" | "on":
                            conjugation.third_person_singular = response_conjugation["verb"]
                        case "nous":
                            conjugation.first_person_plural = response_conjugation["verb"]
                        case "vous":
                            conjugation.second_person_formal = response_conjugation["verb"]
                        case "ils/elles" | "ils" | "elles":
                            conjugation.third_person_plural = response_conjugation["verb"]
                        case "-":
                            conjugation.first_person_singular  = response_conjugation["verb"]
                            conjugation.second_person_singular = response_conjugation["verb"]
                            conjugation.third_person_singular  = response_conjugation["verb"]
                            conjugation.first_person_plural    = response_conjugation["verb"]
                            conjugation.second_person_formal   = response_conjugation["verb"]
                            conjugation.third_person_plural    = response_conjugation["verb"]
                
                #   Since we are using Postgres we can upsert instead of doing this:
                if existing_conjugation == None:
                    log.info(f"Adding {conjugation.infinitive} with tense {conjugation.tense}.")
                    session.add(conjugation)
                else:
                    log.info(f"Updating {conjugation.infinitive} with tense {conjugation.tense}.")
                    await session.merge(conjugation)
                    
            return completion.choices[0].message.content
