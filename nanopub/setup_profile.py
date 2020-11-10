#! /usr/bin/env python3
import os
import re
import shutil
from pathlib import Path
from typing import Union, Tuple

import click
import yaml
from rdflib import Graph, FOAF, BNode, Literal

from nanopub import NanopubClient, Nanopub, profile
from nanopub.definitions import USER_CONFIG_DIR
from nanopub.java_wrapper import JavaWrapper
from nanopub.namespaces import NPX, ORCID

PRIVATE_KEY_FILE = 'id_rsa'
PUBLIC_KEY_FILE = 'id_rsa.pub'
DEFAULT_PRIVATE_KEY_PATH = USER_CONFIG_DIR / PRIVATE_KEY_FILE
DEFAULT_PUBLIC_KEY_PATH = USER_CONFIG_DIR / PUBLIC_KEY_FILE
RSA = 'RSA'
ORCID_ID_REGEX = r'^https://orcid.org/(\d{4}-){3}\d{4}$'


def validate_orcid_id(ctx, orcid_id: str):
    """
    Check if valid ORCID iD, should be https://orcid.org/ + 16 digit in form:
        https://orcid.org/0000-0000-0000-0000
    """
    if not orcid_id:
        return None
    elif re.match(ORCID_ID_REGEX, orcid_id):
        return orcid_id
    else:
        raise ValueError('Your ORCID iD is not valid, please provide a valid ORCID iD that '
                         'looks like: https://orcid.org/0000-0000-0000-0000')


@click.command(help='Interactive CLI to create a nanopub user profile. A local version of the profile will be stored '
                    'in the '
                    'user config dir (by default HOMEDIR/.nanopub/). The profile will also be published to the '
                    'nanopub servers.')
@click.option('--keypair', nargs=2, type=Path,
              prompt=f'If the public and private key you would like to use are not in {USER_CONFIG_DIR}, '
                     f'provide them here. If they are in this directory or you wish to generate new keys, '
                     f'leave empty.',
              help='Your RSA public and private keys with which your nanopubs will be signed',
              default=None)
@click.option('--orcid_id', type=str,
              prompt='What is your ORCID iD (i.e. https://orcid.org/0000-0000-0000-0000)? '
                     'Optionally leave empty',
              help='Your ORCID iD (i.e. https://orcid.org/0000-0000-0000-0000), '
                   'optionally leave empty',
              callback=validate_orcid_id,
              default='')
@click.option('--name', type=str, prompt='What is your full name?', help='Your full name')
@click.option('--publish/--no-publish', type=bool, is_flag=True, default=True,
              help='If true, nanopub will be published to nanopub servers',
              prompt=('Would you like to publish your profile to the nanopub servers? '
                      'This links your ORCID iD to your RSA key, thereby making all your '
                      'publications linkable to you'))
def main(orcid_id, publish, name, keypair: Union[Tuple[Path, Path], None]):
    """
    Interactive CLI to create a user profile.

    Args:
        orcid_id: the users ORCID iD or other form of universal identifier. Example:
            `https://orcid.org/0000-0000-0000-0000`
        publish: if True, profile will be published to nanopub servers
        name: the name of the user
        keypair: a tuple containing the paths to the public and private RSA key to be used to sign
            nanopubs. If empty, new keys will be generated.
    """
    click.echo('Setting up nanopub profile...')

    if not USER_CONFIG_DIR.exists():
        USER_CONFIG_DIR.mkdir()

    if not keypair:
        if _rsa_keys_exist():
            if _check_erase_existing_keys():
                _delete_keys()
                JavaWrapper.make_keys()
                click.echo(f'Your RSA keys are stored in {USER_CONFIG_DIR}')
        else:
            JavaWrapper.make_keys()
            click.echo(f'Your RSA keys are stored in {USER_CONFIG_DIR}')
    else:
        public_key_path, private_key = keypair

        # Copy the keypair to the default location
        shutil.copy(public_key_path, USER_CONFIG_DIR / PUBLIC_KEY_FILE)
        shutil.copy(private_key, USER_CONFIG_DIR / PRIVATE_KEY_FILE)

        click.echo(f'Your RSA keys have been copied to {USER_CONFIG_DIR}')

    # Public key can always be found at DEFAULT_PUBLIC_KEY_PATH. Either new keys have been generated there or
    # existing keys have been copy to that location.
    public_key_path = DEFAULT_PUBLIC_KEY_PATH
    public_key = public_key_path.read_text()

    profile_nanopub_uri = None

    # Declare the user to nanopub
    if publish:
        assertion, concept = _create_this_is_me_rdf(orcid_id, public_key, name)
        np = Nanopub.from_assertion(assertion, introduces_concept=concept, nanopub_author=orcid_id,
                                    attributed_to=orcid_id)

        client = NanopubClient()
        result = client.publish(np)

        profile_nanopub_uri = result['concept_uri']

    # Keys are always stored or copied to default location
    profile.store_profile(name, orcid_id, public_key_path, DEFAULT_PRIVATE_KEY_PATH,
                          profile_nanopub_uri)


def _delete_keys():
    os.remove(DEFAULT_PUBLIC_KEY_PATH)
    os.remove(DEFAULT_PRIVATE_KEY_PATH)


def _create_this_is_me_rdf(orcid_id: str, public_key: str, name: str) -> Tuple[Graph, BNode]:
    """
    Create a set of RDF triples declaring the existence of the user with associated ORCID iD.
    """
    my_assertion = Graph()

    key_declaration = BNode('keyDeclaration')
    orcid_node = ORCID[orcid_id]

    my_assertion.add((key_declaration, NPX.declaredBy, orcid_node))
    my_assertion.add((key_declaration, NPX.hasAlgorithm, Literal(RSA)))
    my_assertion.add((key_declaration, NPX.hasPublicKey, Literal(public_key)))
    my_assertion.add((orcid_node, FOAF.name, Literal(name)))

    return my_assertion, key_declaration


def _rsa_keys_exist():
    return DEFAULT_PRIVATE_KEY_PATH.exists() or DEFAULT_PUBLIC_KEY_PATH.exists()


def _check_erase_existing_keys():
    return click.confirm('It seems you already have RSA keys for nanopub. Would you like to replace them?',
                         default=False)


if __name__ == '__main__':
    main()
