#!/usr/bin/env python
"""
LPShipit script will merge all commits from a given feature branch
as a single non fast forward merge, while adding the proper agreed upon
commit message formatting.

Once run in the directory of your cloned repo it will prompt which branches
to merge. This does not push any changes.

lpshipit depend on ``launchpadlib``, which isn't
necessarily up-to-date in PyPI, so we install it from the archive::

`sudo apt-get install python-launchpadlib` OR

`sudo apt-get install python3-launchpadlib` OR

As we're using ``launchpadlib`` from the archive (which is therefore
installed in the system), you'll need to create your virtualenvs
with the ``--system-site-packages`` option.

Activate your virtualenv and install the requirements::

`pip install -r requirements.txt`


"""
import os

import click
import git
import urwid

from launchpadlib.launchpad import Launchpad
from launchpadlib.credentials import UnencryptedFileCredentialStore


def _get_launchpad_client():
    cred_location = os.path.expanduser('~/.lp_creds')
    credential_store = UnencryptedFileCredentialStore(cred_location)
    return Launchpad.login_with('cpc', 'production', version='devel',
                                credential_store=credential_store)


def _format_git_branch_name(branch_name):
    if branch_name.startswith('refs/heads/'):
        return branch_name[len('refs/heads/'):]
    return branch_name


def summarize_mps(mps):
    mp_content = []
    for mp in mps:
        if getattr(mp, 'source_git_repository', None):
            review_vote_parts = []
            approval_count = 0
            for vote in mp.votes:
                if not vote.is_pending:
                    review_vote_parts.append(vote.reviewer.name)
                    if vote.comment.vote == 'Approve':
                        approval_count += 1

            source_repo = mp.source_git_repository
            target_repo = mp.target_git_repository
            source_branch = _format_git_branch_name(mp.source_git_path)
            target_branch = _format_git_branch_name(mp.target_git_path)

            description = '' if mp.description is None else mp.description
            short_description = '' if mp.description is None \
                else mp.description.splitlines()[0]

            mp_content.append({
                'author': mp.registrant.name,
                'description': description,
                'short_description': short_description,
                'reviewers': sorted(review_vote_parts),
                'approval_count': approval_count,
                'web': mp.web_link,
                'target_branch': target_branch,
                'source_branch': source_branch,
                'target_repo': target_repo.display_name,
                'source_repo': source_repo.display_name
            })
    return mp_content


def build_commit_msg(author, reviewers, source_branch, target_branch,
                     commit_message, mp_web_link):
    """Builds the agreed convention merge commit message"""
    return "Merge {} into {} [a={}] [r={}]\n\n{}\n\nMP: {}".format(
        source_branch, target_branch, author,
        reviewers, commit_message, mp_web_link)


@click.command()
@click.option('--directory', default=os.getcwd(), prompt='Which directory',
              help='Path to local directory')
@click.option('--source-branch', help='Source branch name')
@click.option('--target-branch', help='Target Branch name')
@click.option('--mp-owner', help='LP username of the owner of the MP '
                                 '(Defaults to system configured user)',
              default=None)
def lpshipit(directory, source_branch, target_branch, mp_owner):
    """Invokes the commit building with proper user inputs."""
    lp = _get_launchpad_client()
    lp_user = lp.me
    repo = git.Repo(directory)
    local_git = git.Git(directory)
    checkedout_branch = repo.active_branch

    person = lp.people[lp_user.name if mp_owner is None else mp_owner]
    mps = person.getMergeProposals(status=['Needs review', 'Approved'])
    mp_summaries = summarize_mps(mps)
    if mp_summaries:
        mp_options = {"{source_repo}/{source_branch}"
                      "\n->{target_repo}/{target_branch}"
                      "\n    {short_description}"
                      "\n    {approval_count} approvals ({str_reviewers})"
                      "\n    {web}"
                          .format(**mp,
                                  str_reviewers=",".join(mp['reviewers'])):
                          mp
                      for mp in mp_summaries}

        def urwid_exit_on_q(key):
            if key in ('q', 'Q'):
                raise urwid.ExitMainLoop()

        def urwid_exit_program(button):
            raise urwid.ExitMainLoop()

        def mp_chosen(user_args, button, chosen_mp):
            source_branch, target_branch = user_args['source_branch'], \
                                           user_args['target_branch']
            local_branches = [branch.name for branch in repo.branches]

            def source_branch_chosen(user_args, button, chosen_source_branch):
                chosen_mp, target_branch = user_args['chosen_mp'], \
                                           user_args['target_branch']

                def target_branch_chosen(user_args, button, target_branch):

                    source_branch, chosen_mp = user_args['source_branch'], \
                                                   user_args['chosen_mp']

                    if target_branch != source_branch:
                        commit_message = build_commit_msg(
                                author=chosen_mp['author'],
                                reviewers=",".join(
                                        chosen_mp['reviewers']),
                                source_branch=source_branch,
                                target_branch=target_branch,
                                commit_message=chosen_mp[
                                    'description'],
                                mp_web_link=chosen_mp['web']
                        )

                        repo.branches[target_branch].checkout()

                        local_git.execute(
                                ["git", "merge", "--no-ff", source_branch,
                                 "-m", commit_message])

                        merge_summary = "{source_branch} has been merged " \
                                        "in to {target_branch} \nChanges " \
                                        "have _NOT_ been pushed".format(
                                        source_branch=source_branch,
                                        target_branch=target_branch
                                        )

                        merge_summary_listwalker = urwid.SimpleFocusListWalker(
                            list())
                        merge_summary_listwalker.append(
                                urwid.Text(u'Merge Summary'))
                        merge_summary_listwalker.append(
                                urwid.Divider())
                        merge_summary_listwalker.append(
                                urwid.Text(merge_summary))
                        merge_summary_listwalker.append(
                                urwid.Divider())
                        button = urwid.Button("Exit")
                        urwid.connect_signal(button,
                                             'click',
                                             urwid_exit_program)
                        merge_summary_listwalker.append(button)
                        merge_summary_box = urwid.ListBox(
                                merge_summary_listwalker)
                        loop.widget = merge_summary_box

                user_args = {'chosen_mp': chosen_mp,
                             'source_branch': chosen_source_branch}
                if not target_branch:
                    target_branch_listwalker = urwid.SimpleFocusListWalker(
                        list())
                    target_branch_listwalker.append(
                            urwid.Text(u'Target Branch'))
                    target_branch_listwalker.append(urwid.Divider())
                    focus_counter = 1
                    focus = None
                    for local_branch in local_branches:
                        focus_counter = focus_counter + 1
                        button = urwid.Button(local_branch)
                        urwid.connect_signal(button,
                                             'click',
                                             target_branch_chosen,
                                             local_branch,
                                             user_args=[user_args])
                        target_branch_listwalker.append(button)

                        if local_branch == chosen_mp['target_branch']:
                            focus = focus_counter
                        if local_branch == checkedout_branch.name and \
                                        focus is None:
                            focus = focus_counter

                    if focus:
                        target_branch_listwalker.set_focus(focus)

                    target_branch_box = urwid.ListBox(target_branch_listwalker)
                    loop.widget = target_branch_box
                else:
                    target_branch_chosen(user_args, None, target_branch)
            user_args = {'chosen_mp': chosen_mp,
                         'target_branch': target_branch}
            if not source_branch:
                source_branch_listwalker = urwid.SimpleFocusListWalker(list())
                source_branch_listwalker.append(urwid.Text(u'Source Branch'))
                source_branch_listwalker.append(urwid.Divider())
                focus_counter = 1
                focus = None
                for local_branch in local_branches:
                    focus_counter = focus_counter + 1
                    button = urwid.Button(local_branch)
                    urwid.connect_signal(button, 'click',
                                         source_branch_chosen,
                                         local_branch,
                                         user_args=[user_args])
                    source_branch_listwalker.append(button)
                    if local_branch == chosen_mp['source_branch']:
                        focus = focus_counter
                    if local_branch == checkedout_branch.name and \
                                    focus is None:
                        focus = focus_counter

                if focus:
                    source_branch_listwalker.set_focus(focus)

                source_branch_box = urwid.ListBox(source_branch_listwalker)
                loop.widget = source_branch_box
            else:
                source_branch_chosen(user_args, None, source_branch)

        listwalker = urwid.SimpleFocusListWalker(list())
        listwalker.append(urwid.Text(u'Merge Proposal to Merge'))
        listwalker.append(urwid.Divider())
        user_args = {'source_branch': source_branch,
                     'target_branch': target_branch}
        for mp_summary, mp in mp_options.items():
            button = urwid.Button(mp_summary)
            urwid.connect_signal(button, 'click', mp_chosen, mp,
                                 user_args=[user_args])
            listwalker.append(button)

        box = urwid.ListBox(listwalker)
        loop = urwid.MainLoop(box, unhandled_input=urwid_exit_on_q)
        loop.run()

    else:
        print("You have no Merge Proposals in either "
              "'Needs review' or 'Approved' state")


if __name__ == "__main__":
    lpshipit()
