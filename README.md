<h1>Brooklyn Community Board 2 Health, Environment & Social Services Agenda Explorer</h1>

<h2>Prepare to attend your first [BK CB2 HESS meeting](https://cbbrooklyn.cityofnewyork.us/cb2/all-committees/health-environment-social-services/) by looking up past meeting agendas.</h2>

Community boards are an important part of NYC's government, giving residents a voice in what goes on in their neighborhoods. I've been going to my community board's--Brooklyn Community Board 2--meetings for a while now, but I've often felt like I lacked context from previous meetings. What locations attract the most attention? What local businesses near me trying to do? What have been my community's major concerns?

So I made this site in order to go into these meetings prepared to understand and ask critical questions, and be a more engaged citizen in my local government.

<h2>Workflow</h2>
1. Downloaded the agenda pdf's from [Google Drive](https://drive.google.com/drive/folders/1vP5RRdeO7Hq4skAh3kF3caUOAseeP27w)
2. Converted the pdf's to Markdown docling (for basic Markdown) and pymupdf (for links)
3. Gave gpt-4o the parsed Markdown and images of the pdf's to correct any conversion errors
4. Instructed gpt-4o to parse out any business applications. These are an important part of HESS meetings and where a lot of the most exciting conversations happen.
5. Inferred geo coordinates using geopy
6. Use sentence-transformers and FAISS to create a semantic search function
7. Cursor vibe-coded my way to a functioning website built with FastAPI
8. Deployed using Railway

<h2>Notes</h2>
* Multimodal pdf conversion worked surprisingly well
* The business application parsing mostly works but could use some improvement (e.g., couldn't figure out when to use section headers vs. tags)
* geopy location inference generally worked but missed a few items

<h2>Future Plans</h2>
* Expand to other CB2 committees
* Iterate on business application parsing
* Add in process for manual corrections
* Expand to other community boards