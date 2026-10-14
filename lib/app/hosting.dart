/// Where the app fetches its data on first run: the public Hugging Face bucket that holds `index.json` and the pack
/// archives. The address must stay public: the app never carries a token.
const kDefaultDataAddress = 'https://huggingface.co/buckets/chainuser1/scriptura/resolve/';
