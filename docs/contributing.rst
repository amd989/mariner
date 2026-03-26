Contributing
============

.. highlight:: bash

Contributions to Mariner 2 are welcome! Both code and documentation are hosted on
our `GitHub repository <https://github.com/luizribeiro/mariner>`_.  If you
are not familiar with GitHub and Pull Requests, we recommend for you to read
`GitHub's documentation
<https://docs.github.com/en/github/collaborating-with-pull-requests/proposing-changes-to-your-work-with-pull-requests/about-pull-requests>`_.

This document will guide you through setting up your development environment to
:ref:`develop mariner itself <Development>` and
:ref:`write documentation <Documentation>`.

Before diving into the sections below, make sure you have a checkout of the
`mariner git repository <https://github.com/luizribeiro/mariner>`_::

   $ git clone https://github.com/luizribeiro/mariner.git


Development
-----------

Mariner 2 is developed largely on top of `Python <https://www.python.org/>`_,
`TypeScript <https://www.typescriptlang.org/>`_ and `React
<https://reactjs.org/>`_.

If you are interested to help with development, first make sure that you have
`Python 3.7 (or newer) <https://www.python.org/downloads/>`_ installed. We also
use `Poetry <https://python-poetry.org/>`_ for dependency management, so you
should have that installed as well.

If you would like to do frontend development, you should have `node.js
<https://nodejs.org/en/>`_ installed (which includes ``npm``).

Once you have those dependencies installed, you can get your virtual
environment setup with all the required Python dependencies with ``poetry``::

   $ poetry install


Backend
~~~~~~~

The mariner backend code is responsible for serving HTTP requests from the
frontend and communicating with the printer. It's the core of everything and
written in Python. All of the code is within the ``mariner`` directory of the
Git repository.

If you would like to run mariner locally, you can do so with the following
command::

   $ poetry run mariner

.. note::
   Before running mariner locally, you will want to build the frontend's static
   resources first. Make sure to follow the instructions from the :ref:`Frontend
   <Frontend>` section below.

The Pi Zero is a bit too slow for development, so we recommend you to do
development from another machine or use a Raspberry Pi 4 on your printer
which will help considerably, since those models support OTG.

We use `green <https://github.com/CleanCut/green>`_ for running backend tests.
It is installed by Poetry along with the development dependencies, so you can
simply run the backend tests with this command::

   $ poetry green

In addition to running tests, you will want to make sure your code:

* Passes all `Flake8 <https://flake8.pycqa.org/en/latest/>`_ checks:
  ``poetry run flake8``
* Is auto-formatted with `Black <https://black.readthedocs.io/en/stable/>`_:
  ``poetry run black --check .``
* Is type-checked with `pyre <https://pyre-check.org/>`_: ``poetry run pyre``

If you are not familiar with Python type-checking it is recommended for you to
get familiarized with it first, as the mariner code is `strictly typed
<https://pyre-check.org/docs/types-in-python/#strict-mode>`_. `PEP 484
<https://www.python.org/dev/peps/pep-0484/>`_ offers a good overview of the
basic functionality and the ``typing`` `module documentation
<https://docs.python.org/3/library/typing.html>`_ is a great resource as well.


Frontend
~~~~~~~~

The mariner frontend code is largely written in `TypeScript
<https://www.typescriptlang.org/>`_ with `React <https://reactjs.org/>`_. The
UI is built with `Tailwind CSS <https://tailwindcss.com/>`_ and `shadcn/ui
<https://ui.shadcn.com/>`_ components. Data fetching is handled by `React Query
<https://tanstack.com/query>`_. We use `Vite <https://vitejs.dev/>`_ as the
build tool and ``npm`` to manage frontend dependencies.

All of the frontend source code lives in the ``frontend`` directory. So ``cd``
into that directory and install the JS dependencies with::

   $ npm install

In order to run ``mariner`` locally, you will want to package the frontend code
into a static resource that can be served by the backend. Do this with::

   $ npm run build

If successful, the built assets will be generated under the ``dist`` directory.
Now you should be able to run mariner locally with ``poetry run mariner`` as
described on the :ref:`Backend <Backend>` section.

For development, you can run the Vite dev server which proxies API requests to
the Flask backend::

   $ npm run dev

You can run the frontend tests with the following command::

   $ npm test

Just like on the backend, we use a few tools to hold the style guidelines and
best practices of the codebase. So make sure to do these checks on your code:

* `ESLint <https://eslint.org/>`_ issues with: ``npm run lint``


Pre-commit Hooks
~~~~~~~~~~~~~~~~

We run tests, style and typing checks automatically on all commits and pull
requests with a `GitHub Action <https://docs.github.com/en/actions>`_. However,
you can also automatically run those locally before every commit you make with
`pre-commit <https://pre-commit.com/>`_. See pre-commit's `installation instructions
<https://pre-commit.com/#installation>`_ for more information. Once you have
``pre-commit`` installed, setup the mariner hook by running this from your local
repository::

   $ pre-commit install

Once the pre-commit hook is installed, any commits to your local mariner
repository will automatically run all backend and frontend checks that would be
run on the GitHub Action.


Documentation
-------------

All of mariner's documentation (including this document!) is hosted on the
mariner repository itself under the ``docs/`` directory. We use `Read the Docs
<https://readthedocs.org/>`_ to host our documentation, which is formatted with
`reStructuredText
<https://www.sphinx-doc.org/en/master/usage/restructuredtext/basics.html>`_.

If you would like to make changes to the documentation, you can make those from
the GitHub UI itself and submit those as Pull Requests without requiring any
local development.

You can also make changes to the documentation and preview them locally. All you
need is a local checkout of the ``mariner`` repository from GitHub, `Python 3.7
(or newer) <https://www.python.org/downloads/>`_, and `Poetry
<https://python-poetry.org/>`_ installed. For more information on that setup,
refer to the :ref:`Backend` section as the instructions are the same.

To build the documentation locally, just run the following commands::

   $ cd docs
   $ make html

Then just open ``docs/_build/html/index.html`` on your browser.

If you are building the documentation on Windows, there is a ``make.bat`` file
which you can run instead of ``make html``.
