   - An alias in `~/.ssh/config` (recommended) → `"host": "<alias>"`.
   - If the key isn't registered yet, they'll need to generate one (Ed25519
     recommended; ECDSA P-521 or RSA ≥2048-bit also accepted) and register
     the public key through RIKYU's Open OnDemand web portal ("SSH Public
     Key" page) before the first login — point them to that portal by
     name, not a URL, since it isn't one we should be linking to here.