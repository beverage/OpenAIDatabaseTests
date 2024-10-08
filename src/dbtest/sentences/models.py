from enum import auto
import sqlalchemy
from sqlalchemy import Enum, Column, String, Boolean, quoted_name
from sqlalchemy.dialects.postgresql import ENUM as SQLAlchemyEnum

from dbtest.database.engine import async_engine
from dbtest.database.metadata import Base, metadata
from dbtest.utils.prompt_enum import PromptEnum
from dbtest.verbs.models import Tense

class Pronoun(PromptEnum):
    first_person         = auto()
    second_person        = auto()
    third_person         = auto()
    first_person_plural  = auto()
    second_person_plural = auto()
    third_person_plural  = auto()

class DirectObject(PromptEnum):
    none      = auto()
    masculine = auto()
    feminine  = auto()
    plural    = auto()
    random    = auto()

class IndirectPronoun(PromptEnum):
    none      = auto()
    masculine = auto()
    feminine  = auto()
    plural    = auto()
    random    = auto()

class ReflexivePronoun(PromptEnum):
    none          = auto()
    first_person  = auto()
    second_person = auto()
    third_person  = auto()

class Negation(PromptEnum):
    none     = auto()
    pas      = auto()
    jamais   = auto()
    rien     = auto()
    personne = auto()
    plus     = auto()
    aucun    = auto()
    encore   = auto()
    random   = auto()

sentence_table = sqlalchemy.Table("sentences", metadata,
    Column("id", sqlalchemy.Integer, primary_key=True),
    # Column('group_id', ForeignKey('verb_groups.id')),
    Column('infinitive',        String(),               nullable=False),
    Column('auxiliary',         String(),               nullable=False),
    Column('pronoun',           Enum(Pronoun),          nullable=False, default=Pronoun.first_person),
    Column('tense',             Enum(Tense),            nullable=False, default=Tense.present),
    Column('direct_object',     SQLAlchemyEnum(DirectObject,     name=quoted_name('direct_object', True)),     nullable=False, default=DirectObject.none),
    Column('indirect_pronoun',  SQLAlchemyEnum(IndirectPronoun,  name=quoted_name('indirect_pronoun', True)),  nullable=False, default=IndirectPronoun.none),
    Column('reflexive_pronoun', SQLAlchemyEnum(ReflexivePronoun, name=quoted_name('reflexive_pronoun', True)), nullable=False, default=ReflexivePronoun.none),
    Column('negation',          Enum(Negation),         nullable=False, default=Negation.none),
    Column('content',           String(),               nullable=False),
    Column('translation',       String(),               nullable=False),
    Column('is_correct',        Boolean(),              nullable=False, default=True),
    extend_existing=False
)

class Sentence(Base): # pylint: disable=too-few-public-methods
    __table__ = sqlalchemy.Table('sentences', metadata, autoload=True, autoload_with=async_engine)
