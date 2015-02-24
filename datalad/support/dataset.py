# emacs: -*- mode: python-mode; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""
This layer makes the difference between an arbitrary annex and a datalad-managed dataset.

"""
__author__ = 'Benjamin Poldrack'

from os.path import join

from annexrepo import AnnexRepo

class Dataset(AnnexRepo):
    """Representation of a dataset handled by datalad.

    Implementations of datalad commands are supposed to use this rather than AnnexRepo or GitRepo directly,
    since any restrictions on annexes required by datalad due to its cross-platform distribution approach are handled
    within this class. Also an AnnexRepo has no idea of any datalad configuration needs, of course.

    """

    def __init__(self, path, url=None):
        """Creates a dataset representation from path.

        If `path` is empty, it creates an new repository.
        If `url` is given, it is expected to point to a git repository to create a clone from.

        Parameters
        ----------

        path : str
               path to repository

        url: str
             url to the to-be-cloned repository.
             valid git url according to http://www.kernel.org/pub/software/scm/git/docs/git-clone.html#URLS required.

        """

        super(Dataset, self).__init__(path, url)

        # TODO: create proper .datalad-file (or -directory?) for marking as dataset and future use for config
        dataladFile = open(join(self.path,'.datalad'),'w')
        dataladFile.write('dummy')
        dataladFile.close()


    def dummy_dataset_command(self):
        """Just a dummy

        No params, nothing to explain, should raise NotImplementedError.

        """
        raise NotImplementedError
