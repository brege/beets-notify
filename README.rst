============
beets-notify
============

A beets_ plugin to notify your devices and services when new album(s) are imported into your library.

`Apprise`_ is the backend used to send push notifications to your phone, matrix channel, email, push notification service, and many others. Apprise supports nearly *all* notification services.

If your notification service supports it, album art will be embedded in the notification, automatically handled through Apprise's attachment system.

.. _beets: https://github.com/beetbox/beets

.. _apprise: https://github.com/caronc/apprise

Install
-------

**From PyPI (recommended):**

.. code-block:: bash

   $ pipx inject beets beets-notify

**From source (development/testing):**

.. code-block:: bash

   $ git clone https://github.com/brege/beets-notify
   $ cd beets-notify
   $ pipx inject beets -e .

Apprise Urls
------------

Apprise uses `service urls`_. 

Pushover_

.. code-block:: text 

   pover://abcdefghijklmnopqrstuvwxyz1234@xyz1234zbcdefghijklmnopqrstuvw

Email_ (`Fastmail`_ supports 100+ aliased domains)

Using an app-password `1234 5678 5a5c 3b3d` for the main email `account@fastmail.com` using the alias `alias@sent.as`:

.. code-block:: text

   mailto://1234 5678 5a5c 3b3d@sent.as?user=account@fastmail.com&to=alias@sent.as

.. _service urls: https://github.com/caronc/apprise#supported-notifications

.. _Pushover: https://github.com/caronc/apprise/wiki/Notify_pushover

.. _Email: https://github.com/caronc/apprise/wiki/Notify_email

.. _Fastmail: https://github.com/caronc/apprise/wiki/Notify_email-Fastmail

Configuration
-------------

Enable the plugin in your ``~/.config/beets/config.yaml``:

.. code-block:: yaml

    plugins: notify

    notify:
        apprise_urls:
            - "pover://abcdefghijklmnopqrstuvwxyz1234@xyz1234zbcdefghijklmnopqrstuvw"
        truncate: 3                  # albums to enumerate before truncating (...)
        body_maxlength: 1024         # max body chars
        artwork: yes                 # attach artwork
        artwork_maxsize: 0           # max file size in bytes (0 = service limits)
        collage: yes                 # generate NxM collage grid of artwork (max 3x3)

