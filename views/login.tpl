<head>
    <title>Screenly Login</title>
    <link type="text/css" href="/static/css/style.css" rel="Stylesheet" />	
</head>
<body>
    <div class="main">
        <h1>Screenly :: Login</h1>

            <fieldset class="main">
	    %if message:
		<strong>{{message}}</strong>
	    %end
	    %if error:
		<strong class="error">{{error}}</strong>
	    %end
        	<form action="/auth/login" id="login" method="post">
        		<p><strong><label for="name">username:</label></strong>
        		    <input type="text" id="name" name="username" /></p>
        		<p><strong><label for="password">password:</label></strong>
        		    <input type="password" id="password" name="password" /></p>
        		<p><div class="aligncenter"><input type="submit" value="Submit" /></div></p>
        	</form>
            </fieldset>
    </div>
</body>
