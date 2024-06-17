import json
import logging

from sqlalchemy import and_, select

from .prompts import generate_verb_prompt

from ..database.engine import Base, get_async_session
from ..database.verbs import Reflexivity

from ..ai.client import AsyncChatGPTClient

async def fetch_verb(openapi_client: AsyncChatGPTClient, requested_verb: str) -> str:

    Conjugation = Base.classes.conjugations
    Verb = Base.classes.verbs

    logging.info(f"Fetching verb {requested_verb}")

    async with get_async_session() as session:

        logging.info(f"Saving this verb {requested_verb}")

        response: str = await openapi_client.handle_request(prompt=generate_verb_prompt(verb_infinitive=requested_verb))
        response_json: str = json.loads(response)
        infinitive: str = response_json["infinitive"]

        existing_verb: Verb = (
            await session.scalars(select(Verb)
                .filter(Verb.infinitive == requested_verb)
                .order_by(Verb.id.desc()))).first()

        if existing_verb:
            logging.info(f"The verb {infinitive} already exists and will be updated if needed.")
        else:
            logging.info(f"The verb {infinitive} does not yet exist in the database.")

        verb: Verb = Verb() if existing_verb is  None else existing_verb
        verb.auxiliary   = response_json["auxiliary"]
        verb.infinitive  = infinitive
        verb.reflexivity = Reflexivity[response_json["reflexivity"]]

        session.add(verb)
        await session.commit()

        for response_tense in response_json["tenses"]:

            tense = response_tense["tense"]

            existing_conjugation: Conjugation = (
                await session.scalars(select(Conjugation)
                    .filter(and_(Conjugation.infinitive == infinitive, Conjugation.tense == tense))
                    .order_by(Conjugation.id.desc()))).first()

            if existing_conjugation:
                logging.info(f"A verb conjugation for {infinitive}, {tense} already exists and will be updated.")
            else:
                logging.info(f"Verb conjugations are missing or are incomplete for {infinitive} and will be added/updated.")

            conjugation: Conjugation = Conjugation() if existing_conjugation is None else existing_conjugation
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
            if existing_conjugation is None:
                logging.info(f"Adding {conjugation.infinitive} with tense {conjugation.tense}.")
                await session.merge(conjugation)
            else:
                logging.info(f"Updating {conjugation.infinitive} with tense {conjugation.tense}.")
                await session.merge(conjugation)